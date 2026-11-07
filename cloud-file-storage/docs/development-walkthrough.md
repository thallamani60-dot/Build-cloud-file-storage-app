# Development walkthrough

This guide follows one request through the code. The full implementation is in the listed files; this document explains the purpose and execution order of each module so changes can be made without collapsing the layers together.

## Build order and concepts

| Step | File location | Concept and why it is used |
|---|---|---|
| 1 | `app/core/config.py` | Pydantic Settings maps deployment environment variables to typed values. Keeping secrets and limits outside source code lets the same image run in local, test, and cloud environments. |
| 2 | `app/database/base.py`, `app/database/session.py` | SQLAlchemy supplies a shared model registry and request-scoped sessions. The request dependency closes sessions even when a route fails. |
| 3 | `app/models/` and `migrations/` | ORM entities persist accounts and file ownership. Alembic gives production a repeatable, reviewable schema change instead of creating tables implicitly at app startup. |
| 4 | `app/schemas/` | Pydantic schemas validate inputs and whitelist response fields, so password hashes and S3 object keys cannot leak through generic model serialization. |
| 5 | `app/repositories/` | Database query details stay separate from business rules. File lookups are constrained by both file ID and owner ID. |
| 6 | `app/core/security.py`, `app/api/dependencies.py` | Argon2 protects password hashes; JWT verification turns a bearer token into an active database user for each protected request. |
| 7 | `app/services/s3_service.py` | A lazy Boto3 adapter handles private object operations, encryption headers, signed URL creation, and AWS error translation. AWS credentials come from Boto3's provider chain. |
| 8 | `app/services/file_service.py` | Business workflows validate and upload content, store metadata, clean up if metadata creation fails, and stream bytes after checking ownership. |
| 9 | `app/api/routes/` | Routers define REST paths and HTTP behavior. They call services instead of containing SQL or Boto3 logic. |
| 10 | `app/core/handlers.py`, `app/main.py` | Central handlers give clients stable JSON errors; middleware adds a request ID and timing log for CloudWatch correlation. |
| 11 | `infra/`, `Dockerfile`, `docker-compose.yml` | Infrastructure and packaging describe the private bucket, IAM scope, local PostgreSQL, and runtime image. |

## Upload request, in execution order

1. `POST /api/v1/files/upload` in `app/api/routes/file_routes.py` requires a multipart `file`, an authenticated `User`, and a database session.
2. `get_current_user` in `app/api/dependencies.py` reads the OAuth2 bearer token, verifies the JWT signature and expiration, and loads the active user.
3. The route reads at most `MAX_UPLOAD_BYTES + 1` bytes. That extra byte makes an oversized upload detectable without passing an unbounded body into the storage service.
4. `file_service.upload_file` calls `validate_upload`, which extracts a safe basename, checks extension and reported MIME type, enforces the size cap, and checks common binary signatures.
5. The service creates a random owner-scoped object key. The original filename never participates in the key.
6. `s3_service.upload_bytes` uses Boto3 `put_object`, includes the trusted content type and owner metadata, and requests SSE-S3 or the configured KMS key.
7. `file_repository.create` commits only public file metadata and its private object key to PostgreSQL.
8. If metadata persistence fails after the S3 write, the service attempts to delete that new object before returning the database error.
9. `FileRead` shapes the successful `201` response without exposing the object key.

## Download request, in execution order

1. `GET /api/v1/files/{file_id}/download` validates the UUID and resolves the bearer token to the current user.
2. `file_repository.get_owned` searches for both `file_id` and `owner_id`; it does not reveal whether a different user's record exists.
3. `s3_service.get_object` fetches the private object and maps missing-key, permission, and availability errors to safe API errors.
4. The response streams S3 chunks and sets a safe attachment filename, content length, and `Cache-Control: private, no-store`.

## Run and verify

From the project directory:

```powershell
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Expected local checks are `GET /health/live` → `{"status":"alive"}` and `GET /health/ready` → `{"status":"ready","database":"available"}`. Without an S3 bucket, uploads return `503 storage_not_configured`; tests use Moto and do not need AWS.

Run the automated suite with:

```powershell
pytest -q
```

The tests cover registration/login, upload/download/list/delete, filtering and pagination, user isolation, invalid uploads, S3 permission failures, and storage network errors. Moto intercepts Boto3 calls so no real bucket is modified.

## Common errors and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Settings error on startup | Missing production `SECRET_KEY` | Set a high-entropy secret in Secrets Manager and `ENVIRONMENT=production`. |
| `database_unavailable` or readiness fails | Wrong URL, blocked network, or database down | Check `DATABASE_URL`, PostgreSQL health, security groups, and migrations. |
| `storage_not_configured` | Bucket name absent | Set `S3_BUCKET_NAME` and `AWS_REGION`. |
| `storage_permission_error` | Task role or KMS policy is too narrow/misconfigured | Check the task role, bucket name, and optional KMS key policy. |
| Upload returns `415` | Extension, MIME type, or binary signature is invalid | Send an allowed file with its actual MIME type and supported content. |
| Upload returns `413` | File exceeds configured limit | Reduce the file size or set `MAX_UPLOAD_BYTES` deliberately. |
| Login returns `401` | Wrong credentials, expired token, or different signing key across replicas | Log in again and ensure every production replica uses the same secret. |
| Tests cannot bind a local socket on Windows sandbox | Sandbox blocks TestClient's local socketpair | Run tests in an approved environment where local loopback sockets are available. |
