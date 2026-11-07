# Deployment guide

## Local Docker Compose

1. Copy `.env.example` to `.env` and replace the sample `SECRET_KEY` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Set `S3_BUCKET_NAME` and `AWS_REGION` for a private bucket.
3. For a local AWS CLI profile, set `AWS_CONFIG_DIR` to the host `.aws` directory and include `docker-compose.aws-profile.yml`; it mounts the directory read-only. Do not put access keys in the env file.
4. Run `docker compose up --build`. Compose waits for PostgreSQL, applies Alembic migrations, then starts Uvicorn on port 8000.

## AWS resources

### S3

Create the encrypted bucket and public-access protections:

```powershell
aws cloudformation deploy `
  --template-file infra/s3-bucket.yaml `
  --stack-name cloud-file-storage-bucket `
  --parameter-overrides BucketName=your-globally-unique-bucket-name
```

Replace `REPLACE_WITH_BUCKET_NAME` in `infra/iam-policy.json`, create an IAM policy from it, and attach it to the ECS task role. The policy supports only the application's put/get/delete object operations.

If using `S3_KMS_KEY_ID`, also grant the ECS task role `kms:GenerateDataKey` and `kms:Decrypt` on only that KMS key, and allow the role in the key policy.

### ECS/Fargate, RDS, and secrets

1. Build and push the Docker image to ECR.
2. Place ECS tasks and PostgreSQL RDS in private subnets. Expose the service through an ALB listener with an ACM TLS certificate.
3. Permit the task security group to reach the database security group on PostgreSQL's port. Keep RDS private and enable backups/encryption.
4. Give the ECS task role the S3 object policy. Give the separate task execution role permission to pull ECR images and publish logs.
5. Store `SECRET_KEY` and `DATABASE_URL` in Secrets Manager and map them to container environment variables. Set `ENVIRONMENT=production`, bucket, region, `MAX_UPLOAD_BYTES`, and `RATE_LIMIT_STORAGE_URI` as environment configuration. Startup rejects an absent or sample JWT secret in production mode.
6. Set `RUN_MIGRATIONS=false` on production service tasks. Run a one-off release task with command `alembic upgrade head`; only start or route traffic to the new service after it succeeds.
7. Configure container health checks against `/health/live` and ALB readiness against `/health/ready`.

## CloudWatch

The application writes newline-delimited JSON to stdout. Configure the ECS log driver with a dedicated log group and retention period. Useful alarms include:

- ALB target 5xx count and elevated target response time.
- ECS task restart count, CPU, memory, and desired-versus-running task count.
- RDS CPU, connections, storage pressure, and failover events.
- S3 4xx/5xx request metrics and unexpected request volume.
- Application log filters for `database_unavailable`, `storage_unavailable`, and repeated `storage_permission_error` events.

Never publish secrets or request authorization headers into CloudWatch logs.
