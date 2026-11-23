import pytest
from fastapi.testclient import TestClient

from app.api.search import get_search_service
from app.domain.models import Post
from app.main import app
from app.services.search_service import (
    InvalidLimitError,
    InvalidQueryError,
    SearchService,
)
from tests.fakes import KeywordEncoder

POSTS = [
    Post(id=1, user_id=1, content="my cat sleeps all day"),
    Post(id=2, user_id=2, content="pizza and pasta tonight"),
    Post(id=3, user_id=3, content="writing python code"),
    Post(id=4, user_id=1, content="cat and dog friends"),
]


@pytest.fixture
def service() -> SearchService:
    return SearchService(KeywordEncoder(), POSTS)


@pytest.fixture
def client(service):
    # No `with TestClient(...)`: startup (and the real model) is skipped.
    app.dependency_overrides[get_search_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- service ---------------------------------------------------------------

def test_service_returns_best_match_first(service):
    hits = service.search("pizza", limit=2)
    assert hits[0].post_id == 2
    assert hits[0].score == pytest.approx(1 / 2**0.5)


def test_service_ties_use_ascending_post_id(service):
    # Posts 1 and 4 both mention "cat" once -> same score for "cat".
    hits = service.search("cat", limit=2)
    assert [h.post_id for h in hits] == [1, 4]
    assert hits[0].score >= hits[1].score


@pytest.mark.parametrize("query", ["", "   "])
def test_service_rejects_blank_query(service, query):
    with pytest.raises(InvalidQueryError):
        service.search(query, limit=5)


@pytest.mark.parametrize("limit", [0, 21])
def test_service_rejects_out_of_range_limit(service, limit):
    with pytest.raises(InvalidLimitError):
        service.search("cat", limit=limit)


def test_service_with_empty_index_returns_no_results():
    assert SearchService(KeywordEncoder(), []).search("cat", limit=5) == []


# --- HTTP ------------------------------------------------------------------

def test_search_endpoint_success(client):
    response = client.get("/search", params={"q": "python code", "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "python code"
    assert len(body["results"]) == 2
    first = body["results"][0]
    assert set(first) >= {"post_id", "user_id", "content", "score"}
    assert first["post_id"] == 3
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "params",
    [
        {},                          # missing q
        {"q": ""},                   # empty q
        {"q": "   "},                # whitespace-only q
        {"q": "cat", "limit": 0},    # limit too small
        {"q": "cat", "limit": 21},   # limit too large
        {"q": "cat", "limit": "x"},  # limit not a number
    ],
)
def test_search_endpoint_client_errors(client, params):
    response = client.get("/search", params=params)
    assert response.status_code == 422
    assert "detail" in response.json()
