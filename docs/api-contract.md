# API contract

- [`GET /feed`](#get-feed): **implemented** (Week 4; `strategy=learned` Week 5)
- [`GET /search`](#get-search): **implemented** (Week 3)
- [`POST /posts`](#post-posts): **implemented** (contract Week 2, code Week 5)
- [Users, follows, likes](#users-follows-likes-week-5): **implemented** (Week 5)

## `GET /feed`

> Status: **implemented** in `app/api/feed.py` (Week 4).

Returns the posts a user should see, ranked by the `for_you` score, by the
learned model (`learned`), or newest first (`chronological`).

### Request

`GET /feed?user_id=<int>&limit=<n>&strategy=<strategy>`

| Parameter  | Type    | Required | Rules |
|------------|---------|----------|-------|
| `user_id`  | integer | yes      | Id of the viewing user. Must exist. |
| `limit`    | integer | no (default `20`) | 1–50 inclusive. |
| `strategy` | string  | no (default `for_you`) | `for_you`, `learned` or `chronological`. |

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

`200 OK`, strategy `learned`: same shape; `score` is the predicted probability of a
like, in (0, 1), from the Lab 5 network (`models/like_model.npz`, see README).

- `posts` has **at most** `limit` items (fewer if there are fewer candidates).
- `user_id` inside a post is the **author**; the top-level `user_id` is the viewer.
- `created_at` is UTC, ISO 8601, without a timezone suffix.
- `for_you`: ordered by **descending `score`**, ties by **ascending `post_id`**.
  `score = 1.0 * freshness + 2.0 * affinity + 1.0 * popularity` (see README).
- `learned`: ordered by **descending `score`**, ties by **ascending `post_id`**.
- `chronological`: ordered by **newest `created_at`**, ties by **ascending `post_id`**.

### Validation and error cases

| Status | When | Example body |
|--------|------|--------------|
| `404 Not Found` | `user_id` does not exist. | `{"detail": "User 999 does not exist."}` |
| `422 Unprocessable Entity` | `user_id` missing or not an integer. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `limit` not an integer, < 1 or > 50. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `strategy` is not `for_you`, `learned` or `chronological`. | FastAPI's standard `{"detail": [...]}` |
| `503 Service Unavailable` | `strategy=learned` but the model could not be loaded. | `{"detail": "The learned model is not loaded."}` |

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

> Status: **implemented** in `app/api/social.py` (Week 5), a thin HTTP layer over
> `PostService.create_post` in `app/services/post_service.py`.
> `GET /posts/{id}` returns the same `Post` body, or `404` `{"detail": "Post 999 does not exist."}`.

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

No authentication, editing, deleting or listing of posts.

---

## Users, follows, likes (Week 5)

> Status: **implemented** in `app/api/social.py`, rules in `app/services/social_service.py`.

| Method and path | Body / query | Success | Errors |
|---|---|---|---|
| `POST /users` | `{"username": "zoe_99"}` (trimmed; 3-30 letters, digits, `_`) | `201` `{"id", "username", "created_at"}` | `422` bad username, `409` username taken |
| `GET /users/{id}` | | `200` same body | `404` `{"detail": "User 999 does not exist."}` |
| `POST /follows` | `{"follower_id": 8, "followee_id": 1}` | `201` `{"follower_id", "followee_id", "created_at"}` | `422` follow yourself, `404` unknown user, `409` already following |
| `DELETE /follows?follower_id=8&followee_id=1` | | `204` no body | `404` not following |
| `POST /likes` | `{"user_id": 8, "post_id": 1}` | `201` `{"user_id", "post_id", "created_at"}` | `404` unknown user or post, `409` already liked |
| `DELETE /likes?user_id=8&post_id=1` | | `204` no body | `404` not liked |

Missing fields or wrong types give FastAPI's standard `422` `{"detail": [...]}`.
A like removes the post from that user's feed candidates; a follow raises the
author's `for_you` affinity.
