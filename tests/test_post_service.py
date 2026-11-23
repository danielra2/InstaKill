import pytest

from app.domain.models import Post, User
from app.services.post_service import (
    MAX_CONTENT_LENGTH,
    InvalidPostContentError,
    PostService,
    UserNotFoundError,
)


class InMemoryPostRepository:
    """Fake repository so the service can be tested without a database."""

    def __init__(self) -> None:
        self.users = {1: User(id=1, username="alice")}
        self.posts: list[Post] = []

    def get_user(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    def add_post(self, post: Post) -> Post:
        saved = post.model_copy(update={"id": len(self.posts) + 1})
        self.posts.append(saved)
        return saved


def make_service() -> tuple[PostService, InMemoryPostRepository]:
    repo = InMemoryPostRepository()
    return PostService(repo), repo


def test_create_post_returns_saved_post():
    service, repo = make_service()

    post = service.create_post(user_id=1, content="  hello world  ")

    assert post.id == 1
    assert post.user_id == 1
    assert post.content == "hello world"
    assert repo.posts == [post]


@pytest.mark.parametrize("content", ["", "   ", "x" * (MAX_CONTENT_LENGTH + 1)])
def test_create_post_rejects_invalid_content(content):
    service, repo = make_service()

    with pytest.raises(InvalidPostContentError):
        service.create_post(user_id=1, content=content)
    assert repo.posts == []


def test_create_post_rejects_unknown_user():
    service, repo = make_service()

    with pytest.raises(UserNotFoundError):
        service.create_post(user_id=999, content="hi")
    assert repo.posts == []
