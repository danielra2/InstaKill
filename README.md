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

## Feed (Week 4)

`GET /feed?user_id=<int>&limit=<1..50>&strategy=for_you|chronological`.
Full contract: [`docs/api-contract.md`](docs/api-contract.md).

```bash
python scripts/seed_db.py          # RESETS and re-seeds users, posts, follows, likes
uvicorn app.main:app --reload
curl "localhost:8000/feed?user_id=1&limit=5"
curl "localhost:8000/feed?user_id=1&strategy=chronological"
```

### How the code is split

| Layer | File | Responsibility |
|---|---|---|
| Data | `app/db/database.py`, `app/db/seed.py` (run via `scripts/seed_db.py`) | `follow` and `like` tables (created at startup); seed with 8 users, 24 posts, 18 follows, 28 likes. |
| Repository | `app/db/feed_repository.py` | `SqliteFeedRepository`: the only feed code that runs SQL. |
| Pure ranking | `app/feed/ranking.py` | `rank_feed(candidates, signals, now, weights, limit)` and `chronological_feed`. Heap-based top-k, no clock, no I/O, inputs not mutated. |
| Service | `app/services/feed_service.py` | `FeedService.get_feed`: validates, reads the clock once, builds signals, calls the ranker. |
| HTTP edge | `app/api/feed.py` | Parses `user_id` / `limit` / `strategy`, maps errors to 404/422, formats JSON. |

### Candidates and cold start

Candidates are **all posts except** the viewer's own posts and posts the viewer
already liked (we do not restrict to followed authors, so small accounts still get
a full feed; following an author boosts their posts through *affinity* instead).

A user who **follows nobody and liked nothing** (in the seed: `heidi`, id 8) has
affinity 0 for every post, so their `for_you` feed is ranked by **freshness +
popularity** only: recent posts that many people liked. They never get an empty
feed while other people's posts exist.

### Signals, formula and default weights

```text
score = 1.0 * freshness + 2.0 * affinity + 1.0 * popularity

freshness  = 0.5 ** (age_hours / 24)            1.0 for a brand-new post, 0.5 after one day
affinity   = 0.5 * [viewer follows the author]
           + 0.5 * (viewer's likes on this author / viewer's likes on their most-liked author)
popularity = likes on this post / most likes on any candidate post
```

Every signal is in [0, 1], so the weights alone decide how much each one counts.
Why these weights: affinity gets **2.0** because the main promise of a "for you"
feed is personal content: a followed author should beat a random popular post.
Freshness and popularity get **1.0** each so that, among posts with similar affinity,
new and well-liked posts come first, and so a cold-start user (affinity 0) still
gets a sensible mix of new and popular posts. The half-life of **24 hours** fits a
social app where posts are mostly read within a day. These are reasoned defaults;
they will be checked against the `chronological` baseline in the Week 7 evaluation.

Ties on score (and on `created_at` for `chronological`) are broken by ascending `post_id`.

### Complexity of one `GET /feed` request

With *C* candidate posts and limit *k*:

- the database reads are one pass each over posts, follows and likes;
- building signals is O(C), plus O(L) to count likes (L = number of likes);
- scoring is O(1) per candidate, so O(C);
- `heapq.nsmallest` keeps only the best *k*: O(C log k) instead of O(C log C) for a full sort.

Total: **O(C log k)** (plus O(L) for the like counts). The first thing to
**precompute** is the per-post part that is the same for every viewer:
**like counts / popularity** (today `post_like_counts()` counts every like on each
request). It could be kept as a `like_count` column updated when a like is added, or
cached and refreshed every few minutes. Freshness depends only on `now`, so it could
also be computed once per request batch instead of once per user.

## Week 5: real data, CRUD and the learned feed

Three things were added this week:

1. **MovieLens data** (`app/db/movielens.py`, run via `scripts/seed_movielens.py`).
2. **CRUD endpoints** for users, posts, follows and likes (`app/api/social.py`).
3. **`GET /feed?strategy=learned`**: ranks posts with the small neural network trained in
   Lab 5 (`models/like_model.npz`); the score is the predicted probability of a like.

```bash
# 1. download https://files.grouplens.org/datasets/movielens/ml-latest-small.zip
#    and put the .zip in the repo folder (it is git-ignored: never commit it)
python scripts/seed_movielens.py               # RESETS the db: 610 users, 9,724 posts, 48,580 likes, 4,310 follows
uvicorn app.main:app --reload                  # first start also builds the search index over 9.7k posts (~1 min on CPU)
curl "localhost:8000/feed?user_id=414&limit=5&strategy=learned"
```

`python scripts/seed_db.py` still gives the small synthetic dataset (the tests use it).

### How MovieLens becomes a social network

| MovieLens | InstaKill |
|---|---|
| user `u` | user `ml_user_<u>` with the same id |
| a movie (rated at least once) | a **post**: content = title, tags = genres (`post_tag` table), `created_at` = time of its **first** rating |
| the user who gave that first rating | the post's **author** |
| a rating **>= 4.0** | a **like**, at the rating's real time |
| A liked **3** posts authored by B (A != B) | A **follows** B, dated at that 3rd like |

These are our own rules (the data has no authors and no follows); they are fixed
constants at the top of `app/db/movielens.py`. Times are the real 1996-2018 times, so
`for_you` freshness is ~0 for every post; `--shift-to-now` moves all times forward so
the last rating is "now".

### The learned strategy

| Layer | File | Responsibility |
|---|---|---|
| Model file | `models/like_model.npz` | Lab 5 output: W1 (6x16), b1, W2 (16x1), b2 = 129 numbers, plus `mu`/`sd` and the signal constants. |
| Pure scorer | `app/feed/learned.py` | `load_model`, `compute_signals` (the 6 Lab 5 signals), `predict` (standardize -> tanh -> sigmoid), `top_k`. |
| Repository | `app/db/feed_repository.py` | new reads: post tags, the viewer's liked-tag counts and like count, likes since a date. |
| Service | `app/services/feed_service.py` | `FeedStrategy.LEARNED`: candidates -> signals -> `predict` -> top k. |

The 6 signals are the ones the model was trained on (Lab 5), computed for the viewer at "now":

```text
freshness  = 0.5 ** (age_days / 1095)                     half life 3 years
affinity   = sum of the viewer's liked-tag counts over the post's tags
             / (viewer's total liked-tag count * number of tags of the post)
popularity = likes in the last 365 days / max of that over all posts
activity   = min(1, log1p(viewer's likes) / log1p(500))
lifetime   = log1p(likes ever) / log1p(max likes ever on any post)
age        = min(1, age_days / 9125)                      capped at 25 years
```

Candidates are the same as for the other strategies (no own posts, no already-liked
posts). Order: descending P(like), ties by ascending `post_id`. A user with no likes
gets affinity 0 and activity 0 and still a full feed. Posts created through
`POST /posts` have no tags, so their affinity is 0. `tests/test_learned.py` checks the
three "golden rows" printed by Lab 5 against `predict`.

### CRUD endpoints

`POST /users`, `GET /users/{id}`, `POST /posts`, `GET /posts/{id}`,
`POST /follows`, `DELETE /follows`, `POST /likes`, `DELETE /likes`.
Full contract with status codes: [`docs/api-contract.md`](docs/api-contract.md).
Rules live in `app/services/social_service.py` and `app/services/post_service.py`;
SQL in `app/db/social_repository.py` and `app/db/post_repository.py`.
New posts appear in the feed immediately; the search index is still built only at startup.

## Week 7: offline evaluation

Which feed strategy puts the posts a user will like into their top 10? A time-split
replay over the seeded MovieLens database, run through the same `FeedService.get_feed`
that `GET /feed` uses. Protocol and limitations: [`docs/evaluation-protocol.md`](docs/evaluation-protocol.md).

```bash
pip install -e ".[dev,eval]"            # eval = pandas + matplotlib, not needed by the API
python scripts/seed_movielens.py
python scripts/evaluate.py              # [--db instakill.db] [--cutoff 2016-02-01] [--seed 42] [--out reports/]
```

| Output | Content |
|---|---|
| `reports/eval_results.csv` | NDCG@10 per user and strategy |
| `reports/baseline_table.md` | means with 95 % bootstrap intervals, `learned` minus the best baseline per slice, run metadata |
| `reports/dashboard.html` | static page with the charts (double-click to open; not served by the API) |

The two first files are byte-identical for the same database and arguments.
Result on the seeded data: `learned` 0.149 vs `popularity` 0.107 mean NDCG@10 over 25 users,
difference `+0.041 [-0.030, +0.126]`: **unclear** overall, a win only for casual users.

## Milestones (see masterplan.md for full details)

W1 Repo+API → W3 CRUD+DB → W4 Feed v0 → W7 Baseline+eval plan → W9 ML+pretrained feature → W11 Profile+optimize → W13 Feature freeze+E2E → W14 Red-team+Demo Day.

At the end of each week: a demonstrable commit/tag.
