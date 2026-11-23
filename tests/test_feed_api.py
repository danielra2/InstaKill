"""API tests for GET /feed over the seeded database (a temporary copy)."""
import pytest
from fastapi.testclient import TestClient

import app.db.database as database
from app.main import app
from app.db.seed import FOLLOWS, LIKES, POSTS, seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Use a throw-away database file so the real instakill.db is never touched.
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    seed()
    # No `with TestClient(...)`: startup (search model loading) is skipped.
    return TestClient(app)


def own_and_liked_post_ids(user_id):
    own = {i for i, (author, _, _) in enumerate(POSTS, start=1) if author == user_id}
    liked = {post_id for uid, post_id in LIKES if uid == user_id}
    return own | liked


def test_for_you_feed_over_seeded_db(client):
    response = client.get("/feed", params={"user_id": 1, "limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 1
    assert body["strategy"] == "for_you"
    posts = body["posts"]
    assert 1 <= len(posts) <= 5
    for p in posts:
        assert {"post_id", "user_id", "content", "created_at", "score"} <= set(p)
    keys = [(-p["score"], p["post_id"]) for p in posts]
    assert keys == sorted(keys)
    assert not {p["post_id"] for p in posts} & own_and_liked_post_ids(1)
    # alice follows bob (2), dave (4) and frank (6): a followed author leads
    followed = {b for a, b in FOLLOWS if a == 1}
    assert posts[0]["user_id"] in followed


def test_chronological_feed_has_no_score_and_is_newest_first(client):
    response = client.get("/feed", params={"user_id": 1, "strategy": "chronological"})

    assert response.status_code == 200
    posts = response.json()["posts"]
    assert len(posts) == len(POSTS) - len(own_and_liked_post_ids(1))  # default limit 20
    assert all("score" not in p for p in posts)
    keys = [(p["created_at"], -p["post_id"]) for p in posts]
    assert keys == sorted(keys, reverse=True)


def test_cold_start_user_still_gets_a_feed(client):
    # heidi (8) follows nobody and liked nothing
    response = client.get("/feed", params={"user_id": 8, "limit": 3})
    assert response.status_code == 200
    assert len(response.json()["posts"]) == 3


def test_unknown_user_is_404(client):
    response = client.get("/feed", params={"user_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"] == "User 999 does not exist."


@pytest.mark.parametrize(
    "params",
    [
        {},                                         # missing user_id
        {"user_id": "abc"},                         # not an int
        {"user_id": 1, "limit": 0},                 # limit too small
        {"user_id": 1, "limit": 51},                # limit too large
        {"user_id": 1, "strategy": "trending"},     # unknown strategy
    ],
)
def test_client_errors_are_422(client, params):
    response = client.get("/feed", params=params)
    assert response.status_code == 422
    assert "detail" in response.json()
