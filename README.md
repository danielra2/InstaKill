# InstaKill — Starter Repo

Mini social-media platform. Mandatory backend: Python + FastAPI + SQLite (default) / PostgreSQL (allowed). See the full brief and grading rubric in `masterplan.md` (course root).

What the instructor provides (this starter):

- `app/main.py` — FastAPI hello-world with `GET /health`
- `app/db/database.py` — SQLite bootstrap (creates tables on startup)
- `app/domain/models.py` — `User` / `Post` schema
- `scripts/seed_db.py` — 5-10 synthetic users/posts
- `tests/test_health.py` — test skeleton

What it does **not** provide: the feed, ranking, ML models, search. Those are the team's work, in the following weeks.

## Running it

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
# other terminal:
curl localhost:8000/health

python scripts/seed_db.py
pytest
```

## Semantic search (Week 3)

`GET /search?q=<text>&limit=<1..20>` returns the seeded posts most similar
in meaning to `q`. Full contract: [`docs/api-contract.md`](docs/api-contract.md).

```bash
python scripts/seed_db.py          # make sure there are posts to search
uvicorn app.main:app --reload      # first start downloads the model (~90 MB)
curl "localhost:8000/search?q=machine%20learning&limit=3"
```

### How the code is split

| Layer | File | Responsibility |
|---|---|---|
| Pure retrieval | `app/search/retrieval.py` | `cosine_similarity` and deterministic `top_k` in NumPy. Vectors in, ordered `(post_id, score)` out. |
| Model adapter | `app/search/encoder.py` | `TextEncoder` protocol + `SentenceTransformerEncoder` (`all-MiniLM-L6-v2`, CPU). Only file that loads a model. |
| Repository | `app/db/post_repository.py` | `SqlitePostRepository.list_posts()`. Only search-related file that runs SQL. |
| Application service | `app/services/search_service.py` | `SearchService`: holds the in-memory index, validates `query`/`limit`, calls encoder + `top_k`. |
| HTTP edge | `app/api/search.py` | Parses `q`/`limit`, maps service errors to HTTP 422, formats the JSON response. |

### Where the index is built, and how it would be refreshed

The index is built **once, at application startup**, in the `lifespan`
function of `app/main.py`: it reads all posts through `SqlitePostRepository`,
encodes their text with `SentenceTransformerEncoder`, and stores a
`SearchService` (posts + vector matrix) in `app.state.search_service`.

Posts added after startup are not searchable yet. When post creation is
implemented, the service that creates a post (`PostService.create_post`)
will, after saving it, also tell the search service about it, either by calling
`SearchService.rebuild_index(...)` with the fresh list of posts (simple, fine
for ~1k posts) or by a future `add_post` method that encodes only the new
post and appends one row to the matrix. Restarting the server also rebuilds
the index.

Tests never load the real model: they inject a small fake encoder
(`tests/fakes.py`) and override the FastAPI dependency.

## Milestones (see masterplan.md for full details)

W1 Repo+API → W3 CRUD+DB → W4 Feed v0 → W7 Baseline+eval plan → W9 ML+pretrained feature → W11 Profile+optimize → W13 Feature freeze+E2E → W14 Red-team+Demo Day.

At the end of each week: a demonstrable commit/tag.
