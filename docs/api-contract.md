# API contract: `POST /posts`

> Status: **contract only, not implemented yet** (Week 2).
> The endpoint will be a thin HTTP layer over `PostService.create_post`
> in `app/services/post_service.py`.

Creates a new post for an existing user.

## Request

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

## Successful response

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

## Validation and error cases

| Status | When | Example body |
|--------|------|--------------|
| `422 Unprocessable Entity` | Body is not valid JSON, a field is missing, or a field has the wrong type (e.g. `"user_id": "abc"`). Produced by FastAPI/Pydantic. | FastAPI's standard `{"detail": [...]}` |
| `422 Unprocessable Entity` | `content` is empty or only whitespace (`InvalidPostContentError`). | `{"detail": "Post content must not be empty."}` |
| `422 Unprocessable Entity` | `content` is longer than 280 characters after trimming (`InvalidPostContentError`). | `{"detail": "Post content must be at most 280 characters."}` |
| `404 Not Found` | No user with `user_id` exists (`UserNotFoundError`). | `{"detail": "User 999 does not exist."}` |

## Mapping from service to HTTP

| Service outcome                 | HTTP status |
|---------------------------------|-------------|
| returns `Post`                  | 201         |
| raises `InvalidPostContentError`| 422         |
| raises `UserNotFoundError`      | 404         |

## Out of scope

No authentication, editing, deleting, listing, feed, ranking, or search.
Those come in later weeks.
