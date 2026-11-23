"""Week 5: the learned scorer (pure functions + the saved Lab 5 model)."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from app.feed.learned import (
    FEATURES,
    PostSignalsInput,
    compute_signals,
    load_model,
    predict,
    top_k,
)

MODEL = load_model()

# Printed by the last cells of Lab 5: signals (FEATURES order) -> P(like).
GOLDEN_ROWS = [
    ([0.020159, 0.15, 0.0, 0.222999, 0.518748, 0.675891], 0.36293),
    ([0.387413, 0.1, 0.0, 0.222999, 0.0, 0.164167], 0.012219),
    ([0.023264, 0.1, 0.0, 0.222999, 0.459336, 0.651094], 0.206008),
]


def test_model_file_matches_lab5():
    assert MODEL.W1.shape == (6, 16) and MODEL.W2.shape == (16, 1)
    assert MODEL.half_life_days == 3 * 365 and MODEL.popularity_days == 365
    assert MODEL.activity_cap == 500 and MODEL.age_cap_days == 25 * 365


@pytest.mark.parametrize("row, expected", GOLDEN_ROWS)
def test_golden_rows(row, expected):
    # rows were rounded to 6 decimals when printed, so allow a tiny difference
    assert predict(MODEL, np.array([row]))[0] == pytest.approx(expected, abs=1e-4)


def test_predict_is_a_probability_and_vectorised():
    x = np.random.default_rng(0).random((1000, len(FEATURES)))
    p = predict(MODEL, x)
    assert p.shape == (1000,)
    assert ((p > 0) & (p < 1)).all()
    assert np.allclose(p[:3], [predict(MODEL, x[i : i + 1])[0] for i in range(3)])


NOW = datetime(2026, 1, 1)


def post(days_old, tags, recent=0, lifetime=0):
    return PostSignalsInput(NOW - timedelta(days=days_old), frozenset(tags), recent, lifetime)


def test_signals_follow_the_lab_formulas():
    # same situation as Lab 5 self-check 1: viewer liked 3 x Drama + 1 x Comedy
    half_life = MODEL.half_life_days
    posts = [post(half_life, {"Drama"}, recent=2, lifetime=2),
             post(half_life, {"Drama", "Comedy"}, recent=0, lifetime=0),
             post(half_life, {"Drama"}, recent=1, lifetime=1)]
    f = compute_signals(MODEL, posts, {"Drama": 3, "Comedy": 1}, viewer_like_count=4,
                        max_recent_likes=2, max_lifetime_likes=2, now=NOW)
    assert f.shape == (3, 6)
    assert f[0, 0] == pytest.approx(0.5)                           # freshness after one half-life
    assert f[0, 1] == pytest.approx(0.75) and f[1, 1] == pytest.approx(0.5)  # affinity
    assert f[0, 2] == pytest.approx(1.0) and f[2, 2] == pytest.approx(0.5)   # popularity
    assert f[0, 3] == pytest.approx(np.log1p(4) / np.log1p(500))   # activity
    assert f[0, 4] == pytest.approx(1.0) and f[1, 4] == 0.0       # lifetime
    assert f[0, 5] == pytest.approx(3 / 25)                        # age: 3 years / 25 years
    assert f.min() >= 0.0 and f.max() <= 1.0


def test_cold_start_viewer_has_zero_affinity_and_activity():
    f = compute_signals(MODEL, [post(10, {"Drama"})], {}, 0, 0, 0, NOW)
    assert f[0, 1] == 0.0 and f[0, 3] == 0.0
    assert np.isfinite(f).all()


def test_no_candidates():
    assert compute_signals(MODEL, [], {}, 0, 0, 0, NOW).shape == (0, 6)


def test_top_k_orders_by_score_then_post_id():
    assert top_k([5, 3, 9, 1], np.array([0.2, 0.9, 0.2, 0.1]), 3) == [1, 0, 2]
    assert top_k([1, 2], np.array([0.5, 0.4]), 10) == [0, 1]
