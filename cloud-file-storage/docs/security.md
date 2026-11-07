# Security notes

## Identity and authorization

- Passwords are hashed with the recommended Argon2 implementation from `pwdlib`; plaintext passwords are not persisted or returned.
- JWTs are signed with HS256, contain a subject and expiration, and expire after the configured interval.
- File lookup always includes the authenticated owner ID. A file owned by someone else is indistinguishable from a missing file (`404`).
- Use a durable high-entropy `SECRET_KEY` from Secrets Manager in production and share it across replicas. The generated fallback is only for local use.

## File handling

- Filenames are reduced to a basename and are never used as S3 keys.
- The API enforces an extension allowlist, accepted MIME types, a configurable byte limit, and signatures for PDF/PNG/JPEG/DOCX.
- Files are returned as attachments. S3 stays private; temporary URLs are signed for GET and have a configurable 60–3600 second lifetime.
- S3 writes request server-side encryption. The bucket template also configures default encryption and blocks all public access. Bucket versioning allows recovery; deleted versions are removed by lifecycle after 30 days, so deletion hides a file immediately but physical version removal is delayed.

## AWS access

Use an ECS task role or another workload identity. The example IAM policy permits only object operations on `users/*` in one bucket. It intentionally has no bucket-wide listing, ACL, policy, or public-access permissions. If `S3_KMS_KEY_ID` is configured, add `kms:GenerateDataKey` and `kms:Decrypt` scoped to that key and allow the task role in the key policy. Restrict the bucket and database to private networking; enforce TLS at the ALB and bucket policy.

## Rate limits and logs

Authentication endpoints are limited to 10 requests per minute per source IP; file endpoints are limited to 60 per minute. The included memory backend is per process. Production should configure a private shared Redis service. JSON logs include request ID, method, path, status, and duration. Do not add credentials, bearer tokens, or file contents to log messages.

## Production checklist

- Set `SECRET_KEY`, database credentials, and any KMS key through Secrets Manager or an equivalent managed secret service.
- Use HTTPS, private subnets, restrictive security groups, and an ECS task role.
- Enable S3 public-access blocks, encryption, versioning, and CloudTrail data events if audit requirements need object-level access history.
- Restrict CORS at the edge if a browser client is added; this API currently does not enable permissive CORS.
- Add account verification, password reset, abuse monitoring, and retention/deletion policies before serving public users.
