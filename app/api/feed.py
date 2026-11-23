"""HTTP edge for the feed: query parsing, error mapping, response formatting."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.feed_repository import SqliteFeedRepository
from app.services.feed_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MIN_LIMIT,
    FeedResult,
    FeedService,
    FeedStrategy,
    FeedUserNotFoundError,
    InvalidFeedLimitError,
)

router = APIRouter()


def get_feed_service() -> FeedService:
    return FeedService(SqliteFeedRepository())


@router.get("/feed", response_model=FeedResult, response_model_exclude_none=True)
def feed(
    user_id: int = Query(..., description="The user who is viewing the feed"),
    limit: int = Query(DEFAULT_LIMIT, ge=MIN_LIMIT, le=MAX_LIMIT),
    strategy: FeedStrategy = Query(FeedStrategy.FOR_YOU),
    service: FeedService = Depends(get_feed_service),
) -> FeedResult:
    try:
        return service.get_feed(user_id=user_id, limit=limit, strategy=strategy)
    except FeedUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidFeedLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
