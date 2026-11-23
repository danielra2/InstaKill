"""Repository for users and posts (search reads, PostService writes)."""
from app.db.database import get_connection
from app.domain.models import Post, User


class SqlitePostRepository:
    """Reads posts from the project's SQLite database."""

    def list_posts(self) -> list[Post]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        return [Post(**dict(row)) for row in rows]

    # ---- Week 5: the PostRepository protocol of PostService (app/services/post_service.py) ----

    def get_user(self, user_id: int) -> User | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, username, created_at FROM user WHERE id = ?", (user_id,)
            ).fetchone()
        return User(**dict(row)) if row else None

    def add_post(self, post: Post) -> Post:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO post (user_id, content) VALUES (?, ?)", (post.user_id, post.content)
            )
            row = conn.execute(
                "SELECT id, user_id, content, created_at FROM post WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            conn.commit()
        return Post(**dict(row))

    def get_post(self, post_id: int) -> Post | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, user_id, content, created_at FROM post WHERE id = ?", (post_id,)
            ).fetchone()
        return Post(**dict(row)) if row else None
