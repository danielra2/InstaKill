"""Week 5: application service for users, follows and likes.

Validation and the rules live here; SQL lives in the repository; HTTP in app/api/social.py.
Each error class says which HTTP status the API maps it to.
"""
import re
from typing import Protocol

from app.domain.models import Follow, Like, User

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")


class SocialError(Exception):
    """Base class for errors of this service."""


class InvalidInputError(SocialError):
    """-> 422. Bad username, following yourself."""


class NotFoundError(SocialError):
    """-> 404. Unknown user/post, or the follow/like to delete does not exist."""


class ConflictError(SocialError):
    """-> 409. Username taken, already following, already liked."""


class SocialRepository(Protocol):
    def add_user(self, username: str) -> User: ...
    def get_user(self, user_id: int) -> User | None: ...
    def post_exists(self, post_id: int) -> bool: ...
    def add_follow(self, follower_id: int, followee_id: int) -> Follow: ...
    def delete_follow(self, follower_id: int, followee_id: int) -> bool: ...
    def add_like(self, user_id: int, post_id: int) -> Like: ...
    def delete_like(self, user_id: int, post_id: int) -> bool: ...


class SocialService:
    def __init__(self, repository: SocialRepository, duplicate_error: type[Exception]) -> None:
        # `duplicate_error`: the exception the repository raises on a UNIQUE violation.
        self._repo = repository
        self._duplicate = duplicate_error

    # ---- users ----
    def create_user(self, username: str) -> User:
        cleaned = username.strip()
        if not USERNAME_PATTERN.fullmatch(cleaned):
            raise InvalidInputError(
                "Username must be 3-30 characters: letters, digits or underscore."
            )
        try:
            return self._repo.add_user(cleaned)
        except self._duplicate as exc:
            raise ConflictError(f"Username '{cleaned}' is already taken.") from exc

    def get_user(self, user_id: int) -> User:
        user = self._repo.get_user(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} does not exist.")
        return user

    # ---- follows ----
    def follow(self, follower_id: int, followee_id: int) -> Follow:
        if follower_id == followee_id:
            raise InvalidInputError("A user cannot follow themselves.")
        self.get_user(follower_id)
        self.get_user(followee_id)
        try:
            return self._repo.add_follow(follower_id, followee_id)
        except self._duplicate as exc:
            raise ConflictError(f"User {follower_id} already follows user {followee_id}.") from exc

    def unfollow(self, follower_id: int, followee_id: int) -> None:
        if not self._repo.delete_follow(follower_id, followee_id):
            raise NotFoundError(f"User {follower_id} does not follow user {followee_id}.")

    # ---- likes ----
    def like(self, user_id: int, post_id: int) -> Like:
        self.get_user(user_id)
        if not self._repo.post_exists(post_id):
            raise NotFoundError(f"Post {post_id} does not exist.")
        try:
            return self._repo.add_like(user_id, post_id)
        except self._duplicate as exc:
            raise ConflictError(f"User {user_id} already liked post {post_id}.") from exc

    def unlike(self, user_id: int, post_id: int) -> None:
        if not self._repo.delete_like(user_id, post_id):
            raise NotFoundError(f"User {user_id} has not liked post {post_id}.")
