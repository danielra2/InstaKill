"""Application service for posts.

Coordinates application behavior around the existing domain models
(`User`, `Post`). It knows nothing about HTTP and never talks to SQLite
directly: storage is reached only through the `PostRepository` protocol,
which a later week will implement on top of `app/db/database.py`.
"""
from typing import Protocol

from app.domain.models import Post, User

MAX_CONTENT_LENGTH = 280


class PostServiceError(Exception):
    """Base class for errors raised by the post service."""


class InvalidPostContentError(PostServiceError):
    """The post content is empty, only whitespace, or too long."""


class UserNotFoundError(PostServiceError):
    """The author of the post does not exist."""


class PostRepository(Protocol):
    """What the service needs from storage. Implemented later (SQLite)."""

    def get_user(self, user_id: int) -> User | None: ...

    def add_post(self, post: Post) -> Post: ...


class PostService:
    """Public entry point for post-related application behavior."""

    def __init__(self, repository: PostRepository) -> None:
        self._repository = repository

    def create_post(self, user_id: int, content: str) -> Post:
        """Validate and create a new post for an existing user.

        Raises:
            InvalidPostContentError: content is blank or longer than
                MAX_CONTENT_LENGTH characters (after trimming whitespace).
            UserNotFoundError: no user with `user_id` exists.
        """
        cleaned = content.strip()
        if not cleaned:
            raise InvalidPostContentError("Post content must not be empty.")
        if len(cleaned) > MAX_CONTENT_LENGTH:
            raise InvalidPostContentError(
                f"Post content must be at most {MAX_CONTENT_LENGTH} characters."
            )

        if self._repository.get_user(user_id) is None:
            raise UserNotFoundError(f"User {user_id} does not exist.")

        return self._repository.add_post(Post(user_id=user_id, content=cleaned))
