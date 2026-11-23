"""Week 5: CRUD endpoints for users, posts, follows and likes."""
import pytest
from fastapi.testclient import TestClient

import app.db.database as database
from app.db.seed import seed
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    seed()  # 8 users (alice=1 ... heidi=8), 24 posts
    return TestClient(app)


def test_create_and_get_user(client):
    r = client.post("/users", json={"username": "  zoe_99 "})
    assert r.status_code == 201
    user = r.json()
    assert user["username"] == "zoe_99" and user["id"] == 9 and user["created_at"]
    assert client.get("/users/9").json() == user


@pytest.mark.parametrize("username, status", [("alice", 409), ("ab", 422), ("has space", 422), ("x" * 31, 422)])
def test_bad_usernames(client, username, status):
    assert client.post("/users", json={"username": username}).status_code == status


def test_unknown_user_is_404(client):
    r = client.get("/users/999")
    assert r.status_code == 404 and r.json() == {"detail": "User 999 does not exist."}


def test_create_post_follows_the_week2_contract(client):
    r = client.post("/posts", json={"user_id": 1, "content": "  hello from week 5  "})
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "hello from week 5" and body["user_id"] == 1 and body["id"] == 25
    assert client.get("/posts/25").json() == body
    assert client.post("/posts", json={"user_id": 1, "content": "   "}).json() == {"detail": "Post content must not be empty."}
    assert client.post("/posts", json={"user_id": 1, "content": "x" * 281}).status_code == 422
    assert client.post("/posts", json={"user_id": 999, "content": "hi"}).status_code == 404
    assert client.post("/posts", json={"user_id": "abc", "content": "hi"}).status_code == 422
    assert client.get("/posts/999").status_code == 404


def test_new_post_shows_up_in_chronological_feed(client):
    client.post("/posts", json={"user_id": 2, "content": "brand new"})
    feed = client.get("/feed", params={"user_id": 1, "strategy": "chronological", "limit": 1}).json()
    assert feed["posts"][0]["content"] == "brand new"


def test_follow_and_unfollow(client):
    r = client.post("/follows", json={"follower_id": 8, "followee_id": 1})
    assert r.status_code == 201 and r.json()["follower_id"] == 8
    assert client.post("/follows", json={"follower_id": 8, "followee_id": 1}).status_code == 409
    assert client.post("/follows", json={"follower_id": 8, "followee_id": 8}).status_code == 422
    assert client.post("/follows", json={"follower_id": 8, "followee_id": 999}).status_code == 404
    assert client.delete("/follows", params={"follower_id": 8, "followee_id": 1}).status_code == 204
    assert client.delete("/follows", params={"follower_id": 8, "followee_id": 1}).status_code == 404


def test_like_and_unlike_change_the_feed(client):
    def candidate_ids():
        posts = client.get("/feed", params={"user_id": 8, "strategy": "chronological", "limit": 50}).json()["posts"]
        return {p["post_id"] for p in posts}

    assert 1 in candidate_ids()
    r = client.post("/likes", json={"user_id": 8, "post_id": 1})
    assert r.status_code == 201 and r.json()["post_id"] == 1
    assert 1 not in candidate_ids()            # liked posts leave the feed
    assert client.post("/likes", json={"user_id": 8, "post_id": 1}).status_code == 409
    assert client.post("/likes", json={"user_id": 8, "post_id": 999}).status_code == 404
    assert client.post("/likes", json={"user_id": 999, "post_id": 1}).status_code == 404
    assert client.delete("/likes", params={"user_id": 8, "post_id": 1}).status_code == 204
    assert client.delete("/likes", params={"user_id": 8, "post_id": 1}).status_code == 404
    assert 1 in candidate_ids()
