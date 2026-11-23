"""Week 5: the learned "like" scorer from Lab 5, as pure NumPy functions.

`models/like_model.npz` is the network trained in Lab 5 (6 -> 16 tanh -> 1,
129 numbers) plus everything needed to use it: the standardization (`mu`, `sd`),
the signal names and the constants of the signal formulas.

The 6 signals are computed exactly as in the Lab 5 `LiveSignals.features`:

    freshness  = 0.5 ** (age_days / half_life_days)               (half life: 3 years)
    affinity   = sum over the post's tags of the viewer's liked-tag counts
                 / (viewer's total liked-tag count * number of tags of the post)
    popularity = likes on the post in the last `popularity_days` / max of that over all posts
    activity   = min(1, log1p(viewer's likes) / log1p(activity_cap))
    lifetime   = log1p(likes ever on the post) / log1p(max likes ever on any post)
    age        = min(1, age_days / age_cap_days)

No database, no clock, no globals: everything comes in as arguments.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "like_model.npz"
FEATURES = ("freshness", "affinity", "popularity", "activity", "lifetime", "age")
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class LikeModel:
    W1: np.ndarray
    b1: np.ndarray
    W2: np.ndarray
    b2: np.ndarray
    mu: np.ndarray
    sd: np.ndarray
    half_life_days: float
    popularity_days: float
    activity_cap: float
    age_cap_days: float


@dataclass(frozen=True)
class PostSignalsInput:
    """What we know about one candidate post."""
    created_at: datetime
    tags: frozenset[str]
    recent_likes: int    # likes in the last `popularity_days`
    lifetime_likes: int  # likes ever


def load_model(path: Path = DEFAULT_MODEL_PATH) -> LikeModel:
    with np.load(path) as saved:
        names = tuple(str(n) for n in saved["features"])
        if names != FEATURES:
            raise ValueError(f"{path}: expected features {FEATURES}, found {names}")
        return LikeModel(
            W1=saved["W1"], b1=saved["b1"], W2=saved["W2"], b2=saved["b2"],
            mu=saved["mu"], sd=saved["sd"],
            half_life_days=float(saved["half_life_days"]),
            popularity_days=float(saved["popularity_days"]),
            activity_cap=float(saved["activity_cap"]),
            age_cap_days=float(saved["age_cap_days"]),
        )


def predict(model: LikeModel, features: np.ndarray) -> np.ndarray:
    """Raw signals (n, 6), columns in FEATURES order -> P(like) for each row, shape (n,)."""
    x = (np.asarray(features, dtype=float) - model.mu) / model.sd
    hidden = np.tanh(x @ model.W1 + model.b1)
    z = (hidden @ model.W2 + model.b2)[:, 0]
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def compute_signals(
    model: LikeModel,
    posts: Sequence[PostSignalsInput],
    viewer_tag_counts: Mapping[str, int],
    viewer_like_count: int,
    max_recent_likes: int,
    max_lifetime_likes: int,
    now: datetime,
) -> np.ndarray:
    """The 6 signals of one viewer for `posts`, as an (n, 6) array.

    `max_recent_likes` / `max_lifetime_likes` are maxima over ALL posts (not only
    the candidates), as in the lab.
    """
    n = len(posts)
    if n == 0:
        return np.zeros((0, len(FEATURES)))
    age_days = np.array([(now - p.created_at).total_seconds() / SECONDS_PER_DAY for p in posts])
    age_days = np.maximum(age_days, 0.0)
    freshness = 0.5 ** (age_days / model.half_life_days)

    total = float(sum(viewer_tag_counts.values()))
    if total > 0:
        affinity = np.array([
            sum(viewer_tag_counts.get(t, 0) for t in p.tags) / (total * max(len(p.tags), 1))
            for p in posts
        ])
    else:
        affinity = np.zeros(n)

    recent = np.array([p.recent_likes for p in posts], dtype=float)
    popularity = recent / max(max_recent_likes, 1)
    activity = np.full(n, min(1.0, np.log1p(viewer_like_count) / np.log1p(model.activity_cap)))
    lifetime_counts = np.array([p.lifetime_likes for p in posts], dtype=float)
    lifetime = np.log1p(lifetime_counts) / np.log1p(max(max_lifetime_likes, 1))
    age = np.minimum(1.0, age_days / model.age_cap_days)
    return np.column_stack([freshness, affinity, popularity, activity, lifetime, age])


def top_k(post_ids: Sequence[int], scores: np.ndarray, limit: int) -> list[int]:
    """Indices of the `limit` best rows: descending score, ties by ascending post_id."""
    order = np.lexsort((np.asarray(post_ids), -np.asarray(scores)))
    return order[:limit].tolist()
