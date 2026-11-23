import copy
from datetime import datetime, timedelta
from types import MappingProxyType

import pytest

from app.feed.ranking import (
    FeedCandidate,
    FeedSignals,
    FeedWeights,
    chronological_feed,
    freshness,
    rank_feed,
)

NOW = datetime(2026, 1, 1, 12, 0, 0)


def post(post_id, author_id=9, hours_ago=1.0):
    return FeedCandidate(post_id, author_id, f"post {post_id}", NOW - timedelta(hours=hours_ago))


ONLY_FRESHNESS = FeedWeights(freshness=1.0, affinity=0.0, popularity=0.0)
ONLY_POPULARITY = FeedWeights(freshness=0.0, affinity=0.0, popularity=1.0)
ONLY_AFFINITY = FeedWeights(freshness=0.0, affinity=1.0, popularity=0.0)


def ids(ranked):
    return [r.candidate.post_id for r in ranked]


def test_freshness_halves_every_half_life():
    assert freshness(NOW, NOW, 24) == 1.0
    assert freshness(NOW - timedelta(hours=24), NOW, 24) == pytest.approx(0.5)
    assert freshness(NOW + timedelta(hours=5), NOW, 24) == 1.0  # future clamps to 1


def test_orders_by_descending_score():
    candidates = [post(1, hours_ago=30), post(2, hours_ago=1), post(3, hours_ago=10)]
    ranked = rank_feed(candidates, FeedSignals(), NOW, ONLY_FRESHNESS, limit=3)
    assert ids(ranked) == [2, 3, 1]
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_equal_scores_use_ascending_post_id():
    candidates = [post(7), post(3), post(5)]  # same age -> same score
    ranked = rank_feed(candidates, FeedSignals(), NOW, ONLY_FRESHNESS, limit=3)
    assert ids(ranked) == [3, 5, 7]


def test_popularity_and_affinity_signals():
    candidates = [post(1, author_id=2), post(2, author_id=3), post(3, author_id=4)]
    signals = FeedSignals(
        followed_author_ids=frozenset({4}),
        liked_author_counts=MappingProxyType({3: 2, 4: 1}),
        post_like_counts=MappingProxyType({1: 5, 2: 1}),
    )
    assert ids(rank_feed(candidates, signals, NOW, ONLY_POPULARITY, 3)) == [1, 2, 3]
    # author 4: 0.5 (follow) + 0.5 * 1/2 = 0.75; author 3: 0.5 * 2/2 = 0.5
    ranked = rank_feed(candidates, signals, NOW, ONLY_AFFINITY, 3)
    assert ids(ranked) == [3, 2, 1]
    assert [r.score for r in ranked] == pytest.approx([0.75, 0.5, 0.0])


def test_limit_is_respected():
    candidates = [post(i, hours_ago=i) for i in range(1, 11)]
    assert ids(rank_feed(candidates, FeedSignals(), NOW, ONLY_FRESHNESS, 3)) == [1, 2, 3]
    assert len(rank_feed(candidates, FeedSignals(), NOW, ONLY_FRESHNESS, 50)) == 10
    assert rank_feed([], FeedSignals(), NOW, ONLY_FRESHNESS, 5) == []


def test_is_deterministic():
    candidates = [post(i, author_id=i % 3, hours_ago=i % 4) for i in range(1, 30)]
    signals = FeedSignals(
        followed_author_ids=frozenset({1}),
        post_like_counts=MappingProxyType({i: i % 5 for i in range(1, 30)}),
    )
    first = rank_feed(candidates, signals, NOW, FeedWeights(), 10)
    second = rank_feed(list(reversed(candidates)), signals, NOW, FeedWeights(), 10)
    assert first == second


def test_does_not_mutate_inputs():
    candidates = [post(1), post(2, hours_ago=5)]
    signals = FeedSignals(
        followed_author_ids=frozenset({9}),
        liked_author_counts={9: 1},
        post_like_counts={1: 3},
    )
    before = (copy.deepcopy(candidates), copy.deepcopy(signals))
    rank_feed(candidates, signals, NOW, FeedWeights(), 2)
    assert (candidates, signals) == before


def test_now_is_an_argument_not_the_clock():
    candidates = [post(1, hours_ago=1), post(2, hours_ago=48)]
    later = NOW + timedelta(days=30)
    a = rank_feed(candidates, FeedSignals(), later, ONLY_FRESHNESS, 2)
    b = rank_feed(candidates, FeedSignals(), later, ONLY_FRESHNESS, 2)
    assert a == b
    assert a[0].score == pytest.approx(freshness(candidates[0].created_at, later, 24))


def test_chronological_newest_first_with_tie_break():
    candidates = [post(4, hours_ago=2), post(9, hours_ago=1), post(2, hours_ago=2)]
    assert [c.post_id for c in chronological_feed(candidates, 3)] == [9, 2, 4]
