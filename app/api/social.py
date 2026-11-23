"""Week 5: HTTP edge for the CRUD endpoints (users, posts, follows, likes)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.db.post_repository import SqlitePostRepository
from app.db.social_repository import DuplicateError, SqliteSocialRepository
from app.domain.models import Follow, Like, Post, User
from app.services.post_service import InvalidPostContentError, PostService, UserNotFoundError
from app.services.social_service import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    SocialError,
    SocialService,
)

router = APIRouter()


class NewUser(BaseModel):
    username: str


class NewPost(BaseModel):
    user_id: int
    content: str


class NewFollow(BaseModel):
    follower_id: int
    followee_id: int


class NewLike(BaseModel):
    user_id: int
    post_id: int


def get_social_service() -> SocialService:
    return SocialService(SqliteSocialRepository(), duplicate_error=DuplicateError)


def get_post_service() -> PostService:
    return PostService(SqlitePostRepository())


def get_post_repository() -> SqlitePostRepository:
    return SqlitePostRepository()


STATUS = {InvalidInputError: 422, NotFoundError: 404, ConflictError: 409}


def to_http(exc: SocialError) -> HTTPException:
    return HTTPException(status_code=STATUS[type(exc)], detail=str(exc))


# ---- users ----
@router.post("/users", response_model=User, status_code=201)
def create_user(body: NewUser, service: SocialService = Depends(get_social_service)) -> User:
    try:
        return service.create_user(body.username)
    except SocialError as exc:
        raise to_http(exc) from exc


@router.get("/users/{user_id}", response_model=User)
def get_user(user_id: int, service: SocialService = Depends(get_social_service)) -> User:
    try:
        return service.get_user(user_id)
    except SocialError as exc:
        raise to_http(exc) from exc


# ---- posts (contract from Week 2, docs/api-contract.md) ----
@router.post("/posts", response_model=Post, status_code=201)
def create_post(body: NewPost, service: PostService = Depends(get_post_service)) -> Post:
    try:
        return service.create_post(user_id=body.user_id, content=body.content)
    except InvalidPostContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/posts/{post_id}", response_model=Post)
def get_post(post_id: int, repository: SqlitePostRepository = Depends(get_post_repository)) -> Post:
    post = repository.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} does not exist.")
    return post


# ---- follows ----
@router.post("/follows", response_model=Follow, status_code=201)
def follow(body: NewFollow, service: SocialService = Depends(get_social_service)) -> Follow:
    try:
        return service.follow(body.follower_id, body.followee_id)
    except SocialError as exc:
        raise to_http(exc) from exc


@router.delete("/follows", status_code=204)
def unfollow(
    follower_id: int = Query(...),
    followee_id: int = Query(...),
    service: SocialService = Depends(get_social_service),
) -> Response:
    try:
        service.unfollow(follower_id, followee_id)
    except SocialError as exc:
        raise to_http(exc) from exc
    return Response(status_code=204)


# ---- likes ----
@router.post("/likes", response_model=Like, status_code=201)
def like(body: NewLike, service: SocialService = Depends(get_social_service)) -> Like:
    try:
        return service.like(body.user_id, body.post_id)
    except SocialError as exc:
        raise to_http(exc) from exc


@router.delete("/likes", status_code=204)
def unlike(
    user_id: int = Query(...),
    post_id: int = Query(...),
    service: SocialService = Depends(get_social_service),
) -> Response:
    try:
        service.unlike(user_id, post_id)
    except SocialError as exc:
        raise to_http(exc) from exc
    return Response(status_code=204)
