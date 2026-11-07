from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.exceptions import APIError


@lru_cache(maxsize=1)
def get_s3_client():
    options: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.s3_endpoint_url:
        options["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **options)


def _bucket() -> str:
    if not settings.s3_bucket_name:
        raise APIError(503, "storage_not_configured", "Object storage is not configured")
    return settings.s3_bucket_name


def _translate_error(exc: Exception) -> None:
    if isinstance(exc, ClientError):
        response = exc.response
        code = str(response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "NotFound", "404"}:
            raise APIError(404, "object_not_found", "Stored file content was not found") from exc
        if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
            raise APIError(502, "storage_permission_error", "Object storage rejected the request") from exc
        if code in {
            "SlowDown",
            "Throttling",
            "ThrottlingException",
            "ServiceUnavailable",
            "InternalError",
            "RequestTimeout",
        }:
            raise APIError(503, "storage_unavailable", "Object storage is temporarily unavailable") from exc
        raise APIError(502, "storage_error", "Object storage could not complete the request") from exc
    if isinstance(exc, BotoCoreError):
        raise APIError(503, "storage_unavailable", "Object storage is temporarily unavailable") from exc


def upload_bytes(object_key: str, body: bytes, content_type: str, owner_id: str) -> None:
    bucket = _bucket()
    encryption: dict[str, str] = {"ServerSideEncryption": "AES256"}
    if settings.s3_kms_key_id:
        encryption = {
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": settings.s3_kms_key_id,
        }
    try:
        get_s3_client().put_object(
            Bucket=bucket,
            Key=object_key,
            Body=body,
            ContentType=content_type,
            Metadata={"owner-id": owner_id},
            **encryption,
        )
    except (ClientError, BotoCoreError) as exc:
        _translate_error(exc)
        raise


def get_object(object_key: str):
    try:
        return get_s3_client().get_object(Bucket=_bucket(), Key=object_key)
    except (ClientError, BotoCoreError) as exc:
        _translate_error(exc)
        raise


def delete_object(object_key: str) -> None:
    try:
        get_s3_client().delete_object(Bucket=_bucket(), Key=object_key)
    except (ClientError, BotoCoreError) as exc:
        _translate_error(exc)
        raise


def create_presigned_url(object_key: str, expires_in: int | None = None) -> str:
    ttl = expires_in or settings.presigned_url_expire_seconds
    try:
        return get_s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": object_key},
            ExpiresIn=ttl,
        )
    except (ClientError, BotoCoreError) as exc:
        _translate_error(exc)
        raise
