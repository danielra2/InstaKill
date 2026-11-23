"""HTTP edge for search: parses the query string and formats the response."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.services.search_service import (
    MAX_LIMIT,
    MIN_LIMIT,
    SearchError,
    SearchHit,
    SearchService,
)

router = APIRouter()


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


def get_search_service(request: Request) -> SearchService:
    service = getattr(request.app.state, "search_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Search index is not ready.")
    return service


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500, description="Search text"),
    limit: int = Query(5, ge=MIN_LIMIT, le=MAX_LIMIT, description="Max results"),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    try:
        results = service.search(q, limit)
    except SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SearchResponse(query=q, results=results)
