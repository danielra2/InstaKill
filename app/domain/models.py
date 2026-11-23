"""Domain schema: User, Post, Follow, Like. Pydantic models mirroring the SQL DDL in app/db/database.py."""
from datetime import datetime

from pydantic import BaseModel


class User(BaseModel):
    id: int | None = None
    username: str
    created_at: datetime | None = None


class Post(BaseModel):
    id: int | None = None
    user_id: int
    content: str
    created_at: datetime | None = None


class Follow(BaseModel):
    """Week 5: `follower_id` follows `followee_id`."""
    follower_id: int
    followee_id: int
    created_at: datetime | None = None


class Like(BaseModel):
    """Week 5: `user_id` liked `post_id`."""
    user_id: int
    post_id: int
    created_at: datetime | None = None
