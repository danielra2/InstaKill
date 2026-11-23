from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.search import router as search_router
from app.db.database import init_db
from app.db.post_repository import SqlitePostRepository
from app.search.encoder import SentenceTransformerEncoder
from app.services.search_service import SearchService


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Build the in-memory search index once, at startup.
    posts = SqlitePostRepository().list_posts()
    app.state.search_service = SearchService(SentenceTransformerEncoder(), posts)
    yield


app = FastAPI(title="InstaKill", lifespan=lifespan)
app.include_router(search_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
