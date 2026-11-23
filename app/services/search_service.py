"""Application service for semantic search.

Holds a small in-memory index (post vectors) and coordinates encoder +
pure retrieval. No HTTP, no SQLite, no model loading here: the encoder
and the posts are passed in from outside.
"""
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel

from app.domain.models import Post
from app.search.encoder import TextEncoder
from app.search.retrieval import top_k

MIN_LIMIT = 1
MAX_LIMIT = 20


class SearchError(Exception):
    """Base class for errors raised by the search service."""


class InvalidQueryError(SearchError):
    """The query is empty or only whitespace."""


class InvalidLimitError(SearchError):
    """`limit` is outside MIN_LIMIT..MAX_LIMIT."""


class SearchHit(BaseModel):
    post_id: int
    user_id: int
    content: str
    score: float


class SearchService:
    def __init__(self, encoder: TextEncoder, posts: Sequence[Post] = ()) -> None:
        self._encoder = encoder
        self._posts: list[Post] = []
        self._vectors = np.zeros((0, 0), dtype=np.float32)
        self.rebuild_index(posts)

    def rebuild_index(self, posts: Sequence[Post]) -> None:
        """Encode all posts and replace the in-memory index."""
        self._posts = [p for p in posts if p.id is not None]
        if self._posts:
            self._vectors = self._encoder.encode([p.content for p in self._posts])
        else:
            self._vectors = np.zeros((0, 0), dtype=np.float32)

    @property
    def size(self) -> int:
        return len(self._posts)

    def search(self, query: str, limit: int) -> list[SearchHit]:
        """Return up to `limit` posts most similar to `query`.

        Raises:
            InvalidQueryError: `query` is blank.
            InvalidLimitError: `limit` is not in 1..20.
        """
        cleaned = query.strip()
        if not cleaned:
            raise InvalidQueryError("Query must not be empty.")
        if not MIN_LIMIT <= limit <= MAX_LIMIT:
            raise InvalidLimitError(
                f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}."
            )
        if not self._posts:
            return []

        query_vector = self._encoder.encode([cleaned])[0]
        ranked = top_k(
            query_vector, self._vectors, [p.id for p in self._posts], limit
        )
        by_id = {p.id: p for p in self._posts}
        return [
            SearchHit(
                post_id=post_id,
                user_id=by_id[post_id].user_id,
                content=by_id[post_id].content,
                score=score,
            )
            for post_id, score in ranked
        ]
