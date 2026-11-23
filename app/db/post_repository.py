"""Repository boundary: the only search-related code that runs SQL."""
from app.db.database import get_connection
from app.domain.models import Post


class SqlitePostRepository:
    """Reads posts from the project's SQLite database."""

    def list_posts(self) -> list[Post]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        return [Post(**dict(row)) for row in rows]
