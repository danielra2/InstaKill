"""Week 5: seed InstaKill with the MovieLens "ml-latest-small" dataset.

How MovieLens becomes a social network (the same mapping as the Lab 4/5 notebooks):

- every MovieLens user becomes an InstaKill user `ml_user_<id>` (same id);
- every movie that was rated at least once becomes a **post** whose content is the
  movie title, whose tags are the movie's genres, and whose `created_at` is the
  time of the movie's **first rating** ("first seen", as in the labs);
- the **author** of a post is the user who gave that first rating
  (ties on time: the smallest user id);
- every rating **>= 4.0** becomes a **like**, with the real rating time;
- user A **follows** user B when A liked at least `FOLLOW_MIN_LIKES` (3) posts
  authored by B (A != B); the follow is dated at the time of that 3rd like.

`build_dataset` is pure (rows in, rows out); `seed_movielens` writes them.
The MovieLens files are NOT part of the repository: pass their location.
"""
import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.db.database import get_connection, init_db

LIKE_THRESHOLD = 4.0
FOLLOW_MIN_LIKES = 3
MAX_CONTENT_LENGTH = 280
SQL_TIME = "%Y-%m-%d %H:%M:%S"  # the same text format as SQLite's datetime('now')


@dataclass
class MovieLensDataset:
    users: list[tuple[int, str, str]] = field(default_factory=list)  # (id, username, created_at)
    posts: list[tuple[int, int, str, str]] = field(default_factory=list)  # (id, author, content, created_at)
    tags: list[tuple[int, str]] = field(default_factory=list)  # (post_id, tag)
    likes: list[tuple[int, int, str]] = field(default_factory=list)  # (user_id, post_id, created_at)
    follows: list[tuple[int, int, str]] = field(default_factory=list)  # (follower, followee, created_at)


def to_sql_time(ts: int) -> str:
    """Unix seconds -> 'YYYY-MM-DD HH:MM:SS' in UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(SQL_TIME)


def build_dataset(
    ratings: list[dict[str, str]],
    movies: list[dict[str, str]],
    shift_seconds: int = 0,
) -> MovieLensDataset:
    """MovieLens CSV rows (as csv.DictReader gives them) -> InstaKill rows.

    `shift_seconds` is added to every timestamp (0 keeps the real 1996-2018 times).
    """
    events = sorted(
        (int(r["timestamp"]) + shift_seconds, int(r["userId"]), int(r["movieId"]), float(r["rating"]))
        for r in ratings
    )
    titles = {int(m["movieId"]): (m["title"], m["genres"]) for m in movies}

    first_rating: dict[int, tuple[int, int]] = {}  # movie -> (ts, user) of its first rating
    user_first_ts: dict[int, int] = {}
    for ts, user, movie, _ in events:
        first_rating.setdefault(movie, (ts, user))  # events are sorted, so the first one wins
        user_first_ts.setdefault(user, ts)

    data = MovieLensDataset()
    data.users = [(u, f"ml_user_{u}", to_sql_time(ts)) for u, ts in sorted(user_first_ts.items())]

    # post ids follow "first seen" order (oldest movie first), like the labs' row numbers
    post_of: dict[int, int] = {}
    author_of: dict[int, int] = {}
    for post_id, (movie, (ts, author)) in enumerate(
        sorted(first_rating.items(), key=lambda kv: (kv[1][0], kv[0])), start=1
    ):
        title, genres = titles.get(movie, (f"movie {movie}", ""))
        post_of[movie], author_of[post_id] = post_id, author
        data.posts.append((post_id, author, title[:MAX_CONTENT_LENGTH], to_sql_time(ts)))
        data.tags.extend(
            (post_id, g) for g in sorted(set(genres.split("|"))) if g and g != "(no genres listed)"
        )

    liked_from: dict[tuple[int, int], int] = defaultdict(int)  # (fan, author) -> likes so far
    for ts, user, movie, rating in events:
        if rating < LIKE_THRESHOLD:
            continue
        post_id = post_of[movie]
        data.likes.append((user, post_id, to_sql_time(ts)))
        author = author_of[post_id]
        if author != user:
            liked_from[(user, author)] += 1
            if liked_from[(user, author)] == FOLLOW_MIN_LIKES:
                data.follows.append((user, author, to_sql_time(ts)))
    return data


def read_movielens(source: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Read ratings.csv and movies.csv from a folder or from ml-latest-small.zip."""
    source = Path(source)
    if source.is_dir():
        with open(source / "ratings.csv", newline="", encoding="utf-8") as f:
            ratings = list(csv.DictReader(f))
        with open(source / "movies.csv", newline="", encoding="utf-8") as f:
            movies = list(csv.DictReader(f))
        return ratings, movies
    with zipfile.ZipFile(source) as archive:
        def rows(name: str) -> list[dict[str, str]]:
            member = next(n for n in archive.namelist() if n.endswith("/" + name) or n == name)
            with archive.open(member) as raw:
                return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline="")))
        return rows("ratings.csv"), rows("movies.csv")


def write_dataset(data: MovieLensDataset) -> None:
    """RESET the database and insert the dataset."""
    init_db()
    with get_connection() as conn:
        for table in ("post_tag", '"like"', "follow", "post", "user"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('user', 'post')")
        conn.executemany("INSERT INTO user (id, username, created_at) VALUES (?, ?, ?)", data.users)
        conn.executemany(
            "INSERT INTO post (id, user_id, content, created_at) VALUES (?, ?, ?, ?)", data.posts
        )
        conn.executemany("INSERT INTO post_tag (post_id, tag) VALUES (?, ?)", data.tags)
        conn.executemany(
            'INSERT INTO "like" (user_id, post_id, created_at) VALUES (?, ?, ?)', data.likes
        )
        conn.executemany(
            "INSERT INTO follow (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
            data.follows,
        )
        conn.commit()


def seed_movielens(source: Path, shift_to_now: bool = False) -> MovieLensDataset:
    ratings, movies = read_movielens(source)
    shift = 0
    if shift_to_now and ratings:
        last = max(int(r["timestamp"]) for r in ratings)
        shift = int(datetime.now(timezone.utc).timestamp()) - last
    data = build_dataset(ratings, movies, shift_seconds=shift)
    write_dataset(data)
    print(
        f"Seeded MovieLens: {len(data.users)} users, {len(data.posts)} posts, "
        f"{len(data.tags)} tags, {len(data.likes)} likes, {len(data.follows)} follows."
    )
    return data
