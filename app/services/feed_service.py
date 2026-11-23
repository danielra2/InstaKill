"""Application service for the feed.

Orchestrates: repository (data) -> signals -> pure ranking. It reads the
clock here (through an injectable `clock`) and passes `now` to the ranker.
No HTTP and no SQL in this module.
"""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Protocol

from pydantic import BaseModel

from app.domain.models import Post
from app.feed.learned import LikeModel, PostSignalsInput, compute_signals, predict, top_k
from app.feed.ranking import (
    DEFAULT_WEIGHTS,
    FeedCandidate,
    FeedSignals,
    FeedWeights,
    chronological_feed,
    rank_feed,
)

MIN_LIMIT = 1
MAX_LIMIT = 50
DEFAULT_LIMIT = 20


class FeedStrategy(str, Enum):
    FOR_YOU = "for_you"
    CHRONOLOGICAL = "chronological"
    LEARNED = "learned"  # Week 5: the Lab 5 network, score = P(like)


class FeedError(Exception):
    """Base class for feed errors."""


class FeedUserNotFoundError(FeedError):
    """The viewing user does not exist."""


class InvalidFeedLimitError(FeedError):
    """`limit` is outside MIN_LIMIT..MAX_LIMIT."""


class LearnedModelUnavailableError(FeedError):
    """strategy=learned was asked for, but no model was given to the service."""


class FeedRepository(Protocol):
    def user_exists(self, user_id: int) -> bool: ...
    def list_candidate_posts(self, user_id: int) -> list[Post]: ...
    def followed_author_ids(self, user_id: int) -> set[int]: ...
    def liked_author_counts(self, user_id: int) -> dict[int, int]: ...
    def post_like_counts(self) -> dict[int, int]: ...
    def post_tags(self) -> dict[int, frozenset[str]]: ...
    def liked_tag_counts(self, user_id: int) -> dict[str, int]: ...
    def user_like_count(self, user_id: int) -> int: ...
    def post_like_counts_since(self, since: datetime) -> dict[int, int]: ...


class FeedItem(BaseModel):
    post_id: int
    user_id: int
    content: str
    created_at: datetime
    score: float | None = None


class FeedResult(BaseModel):
    user_id: int
    strategy: FeedStrategy
    posts: list[FeedItem]


def utc_now() -> datetime:
    # SQLite's datetime('now') is UTC without a timezone, so compare like with like.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeedService:
    def __init__(
        self,
        repository: FeedRepository,
        weights: FeedWeights = DEFAULT_WEIGHTS,
        clock: Callable[[], datetime] = utc_now,
        like_model: LikeModel | None = None,
    ) -> None:
        self._repository = repository
        self._weights = weights
        self._clock = clock
        self._like_model = like_model

    def get_feed(
        self,
        user_id: int,
        limit: int = DEFAULT_LIMIT,
        strategy: FeedStrategy = FeedStrategy.FOR_YOU,
    ) -> FeedResult:
        if not MIN_LIMIT <= limit <= MAX_LIMIT:
            raise InvalidFeedLimitError(
                f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}."
            )
        if not self._repository.user_exists(user_id):
            raise FeedUserNotFoundError(f"User {user_id} does not exist.")

        candidates = [
            FeedCandidate(
                post_id=p.id,
                author_id=p.user_id,
                content=p.content,
                created_at=p.created_at,
            )
            for p in self._repository.list_candidate_posts(user_id)
        ]

        if strategy is FeedStrategy.LEARNED:
            items = self._learned(user_id, candidates, limit)
        elif strategy is FeedStrategy.CHRONOLOGICAL:
            items = [
                self._item(c, score=None) for c in chronological_feed(candidates, limit)
            ]
        else:
            signals = FeedSignals(
                followed_author_ids=frozenset(
                    self._repository.followed_author_ids(user_id)
                ),
                liked_author_counts=MappingProxyType(
                    self._repository.liked_author_counts(user_id)
                ),
                post_like_counts=MappingProxyType(self._repository.post_like_counts()),
            )
            ranked = rank_feed(candidates, signals, self._clock(), self._weights, limit)
            items = [self._item(r.candidate, score=r.score) for r in ranked]

        return FeedResult(user_id=user_id, strategy=strategy, posts=items)

    def _learned(
        self, user_id: int, candidates: list[FeedCandidate], limit: int
    ) -> list[FeedItem]:
        model = self._like_model
        if model is None:
            raise LearnedModelUnavailableError("The learned model is not loaded.")
        now = self._clock()
        repo = self._repository
        tags = repo.post_tags()
        lifetime = repo.post_like_counts()
        recent = repo.post_like_counts_since(now - timedelta(days=model.popularity_days))
        inputs = [
            PostSignalsInput(
                created_at=c.created_at,
                tags=tags.get(c.post_id, frozenset()),
                recent_likes=recent.get(c.post_id, 0),
                lifetime_likes=lifetime.get(c.post_id, 0),
            )
            for c in candidates
        ]
        features = compute_signals(
            model,
            inputs,
            viewer_tag_counts=repo.liked_tag_counts(user_id),
            viewer_like_count=repo.user_like_count(user_id),
            max_recent_likes=max(recent.values(), default=0),
            max_lifetime_likes=max(lifetime.values(), default=0),
            now=now,
        )
        scores = predict(model, features)
        best = top_k([c.post_id for c in candidates], scores, limit)
        return [self._item(candidates[i], score=float(scores[i])) for i in best]

    @staticmethod
    def _item(c: FeedCandidate, score: float | None) -> FeedItem:
        return FeedItem(
            post_id=c.post_id,
            user_id=c.author_id,
            content=c.content,
            created_at=c.created_at,
            score=score,
        )
