"""Week 5: the MovieLens -> InstaKill mapping, on a tiny hand-made dataset."""
import csv
import sqlite3
import zipfile

import pytest

import app.db.database as database
from app.db.movielens import build_dataset, seed_movielens

MOVIES = [
    {"movieId": "10", "title": "Old Movie (1990)", "genres": "Drama|Comedy"},
    {"movieId": "20", "title": "New Movie (2000)", "genres": "Drama"},
    {"movieId": "30", "title": "Odd Movie (2001)", "genres": "(no genres listed)"},
]
# (user, movie, rating, ts)
RATINGS = [
    (1, 10, 5.0, 100),   # user 1 rates movie 10 first -> author of post 1
    (2, 10, 4.0, 200),   # like
    (2, 20, 3.5, 150),   # user 2 rates movie 20 first -> author of post 2; 3.5 is NOT a like
    (3, 20, 4.5, 300),
    (3, 30, 4.0, 400),   # user 3 is the author of post 3 (movie 30)
    (1, 30, 4.0, 500),
    (1, 20, 4.0, 600),
]


def rows():
    return [{"userId": str(u), "movieId": str(m), "rating": str(r), "timestamp": str(t)}
            for u, m, r, t in RATINGS]


def test_posts_are_movies_in_first_seen_order_with_first_rater_as_author():
    data = build_dataset(rows(), MOVIES)
    assert [(pid, author, content) for pid, author, content, _ in data.posts] == [
        (1, 1, "Old Movie (1990)"),
        (2, 2, "New Movie (2000)"),
        (3, 3, "Odd Movie (2001)"),
    ]
    assert data.posts[0][3] == "1970-01-01 00:01:40"   # created_at = first rating time (ts 100)
    assert sorted(data.tags) == [(1, "Comedy"), (1, "Drama"), (2, "Drama")]
    assert [u[:2] for u in data.users] == [(1, "ml_user_1"), (2, "ml_user_2"), (3, "ml_user_3")]


def test_only_ratings_of_4_or_more_are_likes():
    data = build_dataset(rows(), MOVIES)
    assert {(u, p) for u, p, _ in data.likes} == {(1, 1), (2, 1), (3, 2), (3, 3), (1, 3), (1, 2)}
    assert (2, 2) not in {(u, p) for u, p, _ in data.likes}


def test_follow_after_three_likes_of_the_same_author():
    ratings = [{"userId": "1", "movieId": str(m), "rating": "4", "timestamp": str(m)} for m in (1, 2, 3)]
    ratings += [{"userId": "2", "movieId": str(m), "rating": "5", "timestamp": str(100 + m)} for m in (1, 2, 3)]
    data = build_dataset(ratings, [])
    assert [(a, b) for a, b, _ in data.follows] == [(2, 1)]   # user 2 liked 3 posts by user 1
    assert data.follows[0][2] == "1970-01-01 00:01:43"       # dated at the 3rd like


def test_shift_moves_every_time():
    data = build_dataset(rows(), MOVIES, shift_seconds=86_400)
    assert data.posts[0][3] == "1970-01-02 00:01:40"


@pytest.mark.parametrize("as_zip", [False, True])
def test_seed_from_folder_or_zip(tmp_path, monkeypatch, as_zip):
    folder = tmp_path / "ml-latest-small"
    folder.mkdir()
    with open(folder / "ratings.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["userId", "movieId", "rating", "timestamp"])
        w.writeheader()
        w.writerows(rows())
    with open(folder / "movies.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["movieId", "title", "genres"])
        w.writeheader()
        w.writerows(MOVIES)
    source = folder
    if as_zip:
        source = tmp_path / "ml-latest-small.zip"
        with zipfile.ZipFile(source, "w") as z:
            z.write(folder / "ratings.csv", "ml-latest-small/ratings.csv")
            z.write(folder / "movies.csv", "ml-latest-small/movies.csv")

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    seed_movielens(source)
    seed_movielens(source)  # running twice resets, never duplicates

    conn = sqlite3.connect(tmp_path / "test.db")
    counts = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("user", "post", "post_tag", '"like"')]
    assert counts == [3, 3, 3, 6]
