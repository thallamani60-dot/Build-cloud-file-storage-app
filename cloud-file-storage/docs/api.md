# API examples

The OpenAPI document and interactive client are served at `/openapi.json` and `/docs`.

## Register and authenticate

`POST /api/v1/auth/register` accepts JSON:

```json
{"email":"person@example.com","password":"at-least-twelve-characters"}
```

`POST /api/v1/auth/login` accepts `application/x-www-form-urlencoded` fields `username` (email) and `password`. The response contains `access_token`, `token_type`, and `expires_in` seconds.

## Upload

Send a multipart field named `file` to `POST /api/v1/files/upload` with `Authorization: Bearer <access_token>`. A successful response returns the file UUID, original name, content type, byte size, and creation time. The internal S3 key is never returned.

## List and filter

`GET /api/v1/files?limit=20&offset=0&q=report&extension=pdf` returns:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

`created_from` and `created_to` accept timezone-aware ISO 8601 timestamps. `limit` is 1–100. An extension may be given with or without its leading dot.

## Status behavior

| Status | Meaning |
|---|---|
| 201 | User or file created |
| 204 | File deleted |
| 400 | Invalid filter or filename |
| 401 | Missing, invalid, or expired credentials |
| 404 | File is missing or not owned by the current user |
| 409 | Email already registered |
| 413 | Upload exceeds `MAX_UPLOAD_BYTES` |
| 415 | Extension, MIME type, or binary signature is unsupported |
| 422 | Invalid request shape or parameter |
| 429 | Rate limit exceeded |
| 502 | S3 rejected an operation or returned an unexpected error |
| 503 | Database/storage unavailable or storage is not configured |

All errors use an `error` object with a stable `code` and safe `message`, plus a `request_id` for log correlation.
