"""Seed data and seeding logic for InstaKill (run it with `python scripts/seed_db.py`).

Seeds the InstaKill database with synthetic users, posts, follows and likes.

Running it again RESETS the seeded tables, so the result is always the same
(no duplicated posts). Post times are relative to "now" so that freshness
means something: e.g. post 1 is 70 hours old, post 24 is 1 hour old.
"""
from app.db.database import get_connection, init_db

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi"]

# (author_id, hours_ago, content) -> post ids 1..24 in this order
POSTS = [
    (1, 70, "hello world, this is my first post"),
    (1, 30, "does anyone else think the feed is chronological only? boring"),
    (2, 60, "just shipped a cosine similarity search, feels great"),
    (3, 55, "spam spam spam buy now click here"),
    (4, 50, "benchmarking my ranker against popularity baseline today"),
    (5, 48, "red-team week is going to be brutal, good luck everyone"),
    (2, 20, "numpy broadcasting finally clicked for me"),
    (3, 18, "best cheap pizza near campus? asking for a friend"),
    (4, 16, "heapq.nsmallest is perfect for top-k, no full sort needed"),
    (5, 14, "went for an evening run by the river, highly recommend"),
    (6, 40, "first post here, mostly into photography"),
    (6, 12, "golden hour shots from the old town"),
    (7, 36, "reading a sci-fi novel with a great ending"),
    (7, 10, "any tips for learning type hints in python?"),
    (8, 30, "coffee + lecture notes = productive morning"),
    (8, 9, "our team just passed all the pytest checks"),
    (1, 8, "feed ranking idea: mix freshness with popularity"),
    (2, 7, "fastapi query params validation is so clean"),
    (3, 6, "studying for the exam, send help"),
    (4, 5, "sqlite is underrated for small projects"),
    (5, 4, "live music this weekend, who is going?"),
    (6, 3, "new camera lens arrived today"),
    (7, 2, "library quiet corner is the best place to read"),
    (8, 1, "demo day prep starts now"),
]

# (follower_id, followee_id)
FOLLOWS = [
    (1, 2), (1, 4), (1, 6),
    (2, 1), (2, 4), (2, 8),
    (3, 1), (3, 2),
    (4, 1), (4, 2), (4, 5), (4, 8),
    (5, 6), (5, 7),
    (6, 5), (6, 7), (6, 8),
    (7, 6),
    # user 8 (heidi) follows nobody and likes nothing: the cold-start user
]

# (user_id, post_id)
LIKES = [
    (1, 3), (1, 7), (1, 9), (1, 18),
    (2, 1), (2, 9), (2, 16), (2, 17),
    (3, 3), (3, 7), (3, 17), (3, 18), (3, 9),
    (4, 3), (4, 17), (4, 16), (4, 10),
    (5, 12), (5, 13), (5, 22), (5, 9),
    (6, 10), (6, 21), (6, 23), (6, 24),
    (7, 12), (7, 22), (7, 9),
]


def seed() -> None:
    init_db()
    with get_connection() as conn:
        for table in ("post_tag", '"like"', "follow", "post", "user"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('user', 'post')"
        )
        for user_id, username in enumerate(USERS, start=1):
            conn.execute(
                "INSERT INTO user (id, username) VALUES (?, ?)", (user_id, username)
            )
        for post_id, (user_id, hours_ago, content) in enumerate(POSTS, start=1):
            conn.execute(
                "INSERT INTO post (id, user_id, content, created_at) "
                "VALUES (?, ?, ?, datetime('now', ?))",
                (post_id, user_id, content, f"-{hours_ago} hours"),
            )
        conn.executemany(
            "INSERT INTO follow (follower_id, followee_id) VALUES (?, ?)", FOLLOWS
        )
        conn.executemany('INSERT INTO "like" (user_id, post_id) VALUES (?, ?)', LIKES)
        conn.commit()
    print(
        f"Seeded {len(USERS)} users, {len(POSTS)} posts, "
        f"{len(FOLLOWS)} follows and {len(LIKES)} likes."
    )


if __name__ == "__main__":
    seed()
