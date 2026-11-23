"""Pure feed-ranking functions.

No clock, no database, no HTTP: everything comes in as arguments and the
inputs are never mutated. Same inputs -> same output.

Score of one candidate post p for the viewing user u:

    score = w_freshness  * freshness(p)
          + w_affinity   * affinity(u, author(p))
          + w_popularity * popularity(p)

    freshness  = 0.5 ** (age_hours / half_life_hours)              in (0, 1]
    affinity   = 0.5 * [u follows author]
               + 0.5 * likes_by_u_on_author / max over authors      in [0, 1]
    popularity = likes(p) / max likes over the candidates           in [0, 1]
"""
import heapq
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType


@dataclass(frozen=True)
class FeedCandidate:
    post_id: int
    author_id: int
    content: str
    created_at: datetime


@dataclass(frozen=True)
class FeedSignals:
    """Everything the ranker knows about the viewing user and the posts."""

    followed_author_ids: frozenset[int] = frozenset()
    # author_id -> how many of that author's posts the viewing user liked
    liked_author_counts: Mapping[int, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # post_id -> total number of likes on that post
    post_like_counts: Mapping[int, int] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class FeedWeights:
    freshness: float = 1.0
    affinity: float = 2.0
    popularity: float = 1.0
    half_life_hours: float = 24.0


DEFAULT_WEIGHTS = FeedWeights()


@dataclass(frozen=True)
class RankedPost:
    candidate: FeedCandidate
    score: float


def freshness(created_at: datetime, now: datetime, half_life_hours: float) -> float:
    age_hours = max((now - created_at).total_seconds() / 3600, 0.0)
    return 0.5 ** (age_hours / half_life_hours)


def affinity(author_id: int, signals: FeedSignals, max_author_likes: int) -> float:
    follows = 1.0 if author_id in signals.followed_author_ids else 0.0
    liked = (
        signals.liked_author_counts.get(author_id, 0) / max_author_likes
        if max_author_likes > 0
        else 0.0
    )
    return 0.5 * follows + 0.5 * liked


def popularity(post_id: int, signals: FeedSignals, max_post_likes: int) -> float:
    if max_post_likes <= 0:
        return 0.0
    return signals.post_like_counts.get(post_id, 0) / max_post_likes


def rank_feed(
    candidates: Sequence[FeedCandidate],
    signals: FeedSignals,
    now: datetime,
    weights: FeedWeights,
    limit: int,
) -> list[RankedPost]:
    """Return the `limit` best candidates, highest score first.

    Ties on score are broken by ascending post_id. Uses a heap
    (heapq.nsmallest), so it never sorts all candidates: O(C log k).
    """
    if limit < 1:
        return []
    max_post_likes = max(
        (signals.post_like_counts.get(c.post_id, 0) for c in candidates), default=0
    )
    max_author_likes = max(signals.liked_author_counts.values(), default=0)

    def scored() -> Iterable[RankedPost]:
        for c in candidates:
            score = (
                weights.freshness
                * freshness(c.created_at, now, weights.half_life_hours)
                + weights.affinity * affinity(c.author_id, signals, max_author_likes)
                + weights.popularity
                * popularity(c.post_id, signals, max_post_likes)
            )
            yield RankedPost(candidate=c, score=score)

    return heapq.nsmallest(
        limit, scored(), key=lambda r: (-r.score, r.candidate.post_id)
    )


def chronological_feed(
    candidates: Sequence[FeedCandidate], limit: int
) -> list[FeedCandidate]:
    """Newest first; ties broken by ascending post_id. Also heap-based."""
    if limit < 1:
        return []
    return heapq.nsmallest(
        limit, candidates, key=lambda c: (_newest_first(c.created_at), c.post_id)
    )


def _newest_first(created_at: datetime):
    # A later time gives a smaller key, so heapq.nsmallest returns newest first.
    return datetime.max.replace(tzinfo=created_at.tzinfo) - created_at
