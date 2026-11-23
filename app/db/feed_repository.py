"""Repository boundary for the feed: the only feed code that runs SQL."""
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
