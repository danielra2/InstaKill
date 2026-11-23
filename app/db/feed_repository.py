"""Repository boundary for the feed: the only feed code that runs SQL."""
from datetime import datetime

from app.db.database import get_connection
from app.domain.models import Post


class SqliteFeedRepository:
    def user_exists(self, user_id: int) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT 1 FROM user WHERE id = ?", (user_id,)).fetchone()
        return row is not None

    def list_candidate_posts(self, user_id: int) -> list[Post]:
        """All posts except the user's own posts and posts the user already liked."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.user_id, p.content, p.created_at
                FROM post AS p
                WHERE p.user_id <> :user_id
                  AND NOT EXISTS (
                      SELECT 1 FROM "like" AS l
                      WHERE l.user_id = :user_id AND l.post_id = p.id
                  )
                ORDER BY p.id
                """,
                {"user_id": user_id},
            ).fetchall()
        return [Post(**dict(row)) for row in rows]

    def followed_author_ids(self, user_id: int) -> set[int]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT followee_id FROM follow WHERE follower_id = ?", (user_id,)
            ).fetchall()
        return {row["followee_id"] for row in rows}

    def liked_author_counts(self, user_id: int) -> dict[int, int]:
        """author_id -> number of that author's posts liked by `user_id`."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.user_id AS author_id, COUNT(*) AS n
                FROM "like" AS l JOIN post AS p ON p.id = l.post_id
                WHERE l.user_id = ?
                GROUP BY p.user_id
                """,
                (user_id,),
            ).fetchall()
        return {row["author_id"]: row["n"] for row in rows}

    def post_like_counts(self) -> dict[int, int]:
        """post_id -> total likes (posts without likes are absent)."""
        with get_connection() as conn:
            rows = conn.execute(
                'SELECT post_id, COUNT(*) AS n FROM "like" GROUP BY post_id'
            ).fetchall()
        return {row["post_id"]: row["n"] for row in rows}

    # ---- Week 5: extra reads for the learned strategy ----

    def post_tags(self) -> dict[int, frozenset[str]]:
        """post_id -> its tags (posts without tags are absent)."""
        with get_connection() as conn:
            rows = conn.execute("SELECT post_id, tag FROM post_tag").fetchall()
        tags: dict[int, set[str]] = {}
        for row in rows:
            tags.setdefault(row["post_id"], set()).add(row["tag"])
        return {post_id: frozenset(t) for post_id, t in tags.items()}

    def liked_tag_counts(self, user_id: int) -> dict[str, int]:
        """tag -> how many posts with that tag `user_id` liked."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT t.tag, COUNT(*) AS n
                FROM "like" AS l JOIN post_tag AS t ON t.post_id = l.post_id
                WHERE l.user_id = ?
                GROUP BY t.tag
                """,
                (user_id,),
            ).fetchall()
        return {row["tag"]: row["n"] for row in rows}

    def user_like_count(self, user_id: int) -> int:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT COUNT(*) AS n FROM "like" WHERE user_id = ?', (user_id,)
            ).fetchone()
        return int(row["n"])

    def post_like_counts_since(self, since: datetime) -> dict[int, int]:
        """post_id -> likes with created_at >= `since` (naive UTC)."""
        with get_connection() as conn:
            rows = conn.execute(
                'SELECT post_id, COUNT(*) AS n FROM "like" WHERE created_at >= ? GROUP BY post_id',
                (since.strftime("%Y-%m-%d %H:%M:%S"),),
            ).fetchall()
        return {row["post_id"]: row["n"] for row in rows}
