from datetime import datetime
from uuid import uuid4

from urllib.parse import quote
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import APIError
from app.models import FileRecord
from app.repositories import file_repository
from app.services import s3_service
from app.utils.validators import validate_upload


def upload_file(
    db: Session,
    *,
    owner_id: str,
    filename: str | None,
    content_type: str | None,
    body: bytes,
) -> FileRecord:
    safe_name, safe_content_type = validate_upload(filename, content_type, body)
    object_key = f"users/{owner_id}/objects/{uuid4().hex}"
    s3_service.upload_bytes(object_key, body, safe_content_type, owner_id)
    try:
        return file_repository.create(
            db,
            owner_id=owner_id,
            original_filename=safe_name,
            object_key=object_key,
            content_type=safe_content_type,
            size_bytes=len(body),
        )
    except Exception:
        db.rollback()
        try:
            s3_service.delete_object(object_key)
        except Exception:
            # Preserve the database error; the orphaned S3 object is logged by the caller.
            import logging

            logging.getLogger(__name__).exception("Could not clean up object after metadata failure")
        raise


def _owned_record(db: Session, file_id: str, owner_id: str) -> FileRecord:
    record = file_repository.get_owned(db, file_id, owner_id)
    if not record:
        # Hide whether a file exists for another user.
        raise APIError(404, "file_not_found", "File was not found")
    return record


def get_file(db: Session, file_id: str, owner_id: str) -> FileRecord:
    return _owned_record(db, file_id, owner_id)


def list_files(
    db: Session,
    owner_id: str,
    *,
    limit: int,
    offset: int,
    query: str | None,
    extension: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> tuple[list[FileRecord], int]:
    return file_repository.list_owned(
        db,
        owner_id,
        limit=limit,
        offset=offset,
        query=query,
        extension=extension,
        created_from=created_from,
        created_to=created_to,
    )


def download_file(db: Session, file_id: str, owner_id: str) -> StreamingResponse:
    record = _owned_record(db, file_id, owner_id)
    response = s3_service.get_object(record.object_key)
    body = response["Body"]

    def chunks():
        try:
            yield from body.iter_chunks(chunk_size=64 * 1024)
        finally:
            body.close()

    disposition_name = quote(record.original_filename, safe="")
    return StreamingResponse(
        chunks(),
        media_type=record.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{disposition_name}",
            "Content-Length": str(record.size_bytes),
            "Cache-Control": "private, no-store",
        },
    )


def get_presigned_url(db: Session, file_id: str, owner_id: str) -> str:
    record = _owned_record(db, file_id, owner_id)
    return s3_service.create_presigned_url(record.object_key, settings.presigned_url_expire_seconds)


def delete_file(db: Session, file_id: str, owner_id: str) -> None:
    record = _owned_record(db, file_id, owner_id)
    # Delete the remote object first so a storage error leaves the metadata available for retry.
    s3_service.delete_object(record.object_key)
    file_repository.delete(db, record)
