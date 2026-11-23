"""Week 5: SQL for users, follows and likes (the CRUD part of the API)."""
import sqlite3

from app.db.database import get_connection
from app.domain.models import Follow, Like, User


class DuplicateError(Exception):
    """A UNIQUE / PRIMARY KEY constraint said no (username taken, already following, ...)."""


class SqliteSocialRepository:
    def add_user(self, username: str) -> User:
        try:
            with get_connection() as conn:
                cursor = conn.execute("INSERT INTO user (username) VALUES (?)", (username,))
                row = conn.execute(
                    "SELECT id, username, created_at FROM user WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(str(exc)) from exc
        return User(**dict(row))

    def get_user(self, user_id: int) -> User | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, username, created_at FROM user WHERE id = ?", (user_id,)
            ).fetchone()
        return User(**dict(row)) if row else None

    def post_exists(self, post_id: int) -> bool:
        with get_connection() as conn:
            return conn.execute("SELECT 1 FROM post WHERE id = ?", (post_id,)).fetchone() is not None

    def add_follow(self, follower_id: int, followee_id: int) -> Follow:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO follow (follower_id, followee_id) VALUES (?, ?)",
                    (follower_id, followee_id),
                )
                row = conn.execute(
                    "SELECT follower_id, followee_id, created_at FROM follow "
                    "WHERE follower_id = ? AND followee_id = ?",
                    (follower_id, followee_id),
                ).fetchone()
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(str(exc)) from exc
        return Follow(**dict(row))

    def delete_follow(self, follower_id: int, followee_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM follow WHERE follower_id = ? AND followee_id = ?",
                (follower_id, followee_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def add_like(self, user_id: int, post_id: int) -> Like:
        try:
            with get_connection() as conn:
                conn.execute('INSERT INTO "like" (user_id, post_id) VALUES (?, ?)', (user_id, post_id))
                row = conn.execute(
                    'SELECT user_id, post_id, created_at FROM "like" WHERE user_id = ? AND post_id = ?',
                    (user_id, post_id),
                ).fetchone()
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(str(exc)) from exc
        return Like(**dict(row))

    def delete_like(self, user_id: int, post_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                'DELETE FROM "like" WHERE user_id = ? AND post_id = ?', (user_id, post_id)
            )
            conn.commit()
        return cursor.rowcount > 0
