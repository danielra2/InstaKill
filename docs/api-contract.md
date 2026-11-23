# API contract

- [`GET /feed`](#get-feed): **implemented** (Week 4)
- [`GET /search`](#get-search): **implemented** (Week 3)
- [`POST /posts`](#post-posts): planned, not implemented (Week 2)

## `GET /feed`

> Status: **implemented** in `app/api/feed.py` (Week 4).

Returns the posts a user should see, ranked either by the `for_you` score or
newest first.

### Request

`GET /feed?user_id=<int>&limit=<n>&strategy=<strategy>`

| Parameter  | Type    | Required | Rules |
|------------|---------|----------|-------|
| `user_id`  | integer | yes      | Id of the viewing user. Must exist. |
| `limit`    | integer | no (default `20`) | 1–50 inclusive. |
| `strategy` | string  | no (default `for_you`) | `for_you` or `chronological`. |

Candidates: every post **except** the viewer's own posts and posts the viewer already liked.

### Successful response

`200 OK`, strategy `for_you`:

```json
{
  "user_id": 1,
  "strategy": "for_you",
  "posts": [
    {"post_id": 22, "user_id": 6, "content": "new camera lens arrived today", "created_at": "2026-11-23T08:00:00", "score": 2.917},
    {"post_id": 12, "user_id": 6, "content": "golden hour shots from the old town", "created_at": "2026-11-22T23:00:00", "score": 2.707}
  ]
}
```

`200 OK`, strategy `chronological`: same shape, but posts have **no `score`** field.

- `posts` has **at most** `limit` items (fewer if there are fewer candidates).
- `user_id` inside a post is the **author**; the top-level `user_id` is the viewer.
- `created_at` is UTC, ISO 8601, without a timezone suffix.
- `for_you`: ordered by **descending `score`**, ties by **ascending `post_id`**.
  `score = 1.0 * freshness + 2.0 * affinity + 1.0 * popularity` (see README).
- `chronological`: ordered by **newest `created_at`**, ties by **ascending `post_id`**.

### Validation and error cases

| Status | When | Example body |
|--------|------|--------------|
| `404 Not Found` | `user_id` does not exist. | `{"detail": "User 999 does not exist."}` |
| `422 Unprocessable Entity` | `user_id` missing or not an integer. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `limit` not an integer, < 1 or > 50. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `strategy` is not `for_you` or `chronological`. | FastAPI's standard `{"detail": [...]}` |

---

## `GET /search`

> Status: **implemented** in `app/api/search.py` (Week 3).

Semantic search over the posts in the database. Posts are ranked by the
cosine similarity between the embedding of `q` and the embedding of each
post's `content` (model: `sentence-transformers/all-MiniLM-L6-v2`).

### Request

`GET /search?q=<text>&limit=<n>`

| Parameter | Type    | Required | Rules |
|-----------|---------|----------|-------|
| `q`       | string  | yes      | 1–500 characters, must not be only whitespace. |
| `limit`   | integer | no (default `5`) | 1–20 inclusive. |

Example: `GET /search?q=machine%20learning&limit=2`

### Successful response

`200 OK`

```json
{
  "query": "machine learning",
  "results": [
    {"post_id": 5, "user_id": 4, "content": "benchmarking my ranker against popularity baseline today", "score": 0.31},
    {"post_id": 3, "user_id": 2, "content": "just shipped a cosine similarity search, feels great", "score": 0.22}
  ]
}
```

(Scores above are illustrative.)

- `query` is the original `q`, unchanged.
- `results` has **at most** `limit` items (fewer if there are fewer posts; an empty list if there are no posts).
- `score` is the cosine similarity, a float in [-1, 1].
- Ordering: **descending `score`**; equal scores are ordered by **ascending `post_id`**.

### Validation and error cases

| Status | When |
|--------|------|
| `422 Unprocessable Entity` | `q` is missing or empty (FastAPI validation). |
| `422 Unprocessable Entity` | `q` contains only whitespace: `{"detail": "Query must not be empty."}` |
| `422 Unprocessable Entity` | `limit` is not an integer, or is < 1 or > 20 (FastAPI validation). |
| `503 Service Unavailable`  | The search index has not been built yet (startup not finished). |

---

## `POST /posts`

> Status: **contract only, not implemented yet** (Week 2).
> The endpoint will be a thin HTTP layer over `PostService.create_post`
> in `app/services/post_service.py`.

Creates a new post for an existing user.

### Request

`POST /posts`
`Content-Type: application/json`

```json
{
  "user_id": 1,
  "content": "hello world, this is my first post"
}
```

| Field     | Type    | Required | Rules                                                   |
|-----------|---------|----------|---------------------------------------------------------|
| `user_id` | integer | yes      | Must be the id of an existing user.                     |
| `content` | string  | yes      | Leading/trailing whitespace is trimmed. After trimming: 1–280 characters. |

### Successful response

`201 Created`

```json
{
  "id": 7,
  "user_id": 1,
  "content": "hello world, this is my first post",
  "created_at": "2026-11-23T10:15:00"
}
```

The body is the `Post` domain model (`app/domain/models.py`). `id` and
`created_at` are set by the server.

### Validation and error cases

| Status | When | Example body |
|--------|------|--------------|
| `422 Unprocessable Entity` | Body is not valid JSON, a field is missing, or a field has the wrong type (e.g. `"user_id": "abc"`). Produced by FastAPI/Pydantic. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `content` is empty or only whitespace (`InvalidPostContentError`). | `{"detail": "Post content must not be empty."}` |
| `422 Unprocessable Entity` | `content` is longer than 280 characters after trimming (`InvalidPostContentError`). | `{"detail": "Post content must be at most 280 characters."}` |
| `404 Not Found` | No user with `user_id` exists (`UserNotFoundError`). | `{"detail": "User 999 does not exist."}` |

### Mapping from service to HTTP

| Service outcome                 | HTTP status |
|---------------------------------|-------------|
| returns `Post`                  | 201         |
| raises `InvalidPostContentError`| 422         |
| raises `UserNotFoundError`      | 404         |

### Out of scope

No authentication, editing, deleting, listing, feed, ranking, or search.
Those come in later weeks.
