from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FileRecord


def create(
    db: Session,
    *,
    owner_id: str,
    original_filename: str,
    object_key: str,
    content_type: str,
    size_bytes: int,
) -> FileRecord:
    record = FileRecord(
        owner_id=owner_id,
        original_filename=original_filename,
        object_key=object_key,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_owned(db: Session, file_id: str, owner_id: str) -> FileRecord | None:
    return db.scalar(
        select(FileRecord).where(FileRecord.id == file_id, FileRecord.owner_id == owner_id)
    )


def list_owned(
    db: Session,
    owner_id: str,
    *,
    limit: int,
    offset: int,
    query: str | None = None,
    extension: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[FileRecord], int]:
    filters = [FileRecord.owner_id == owner_id]
    if query:
        filters.append(FileRecord.original_filename.contains(query, autoescape=True))
    if extension:
        filters.append(func.lower(FileRecord.original_filename).like(f"%{extension.lower()}"))
    if created_from:
        filters.append(FileRecord.created_at >= created_from)
    if created_to:
        filters.append(FileRecord.created_at <= created_to)

    total = db.scalar(select(func.count()).select_from(FileRecord).where(*filters)) or 0
    statement = (
        select(FileRecord)
        .where(*filters)
        .order_by(FileRecord.created_at.desc(), FileRecord.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement)), total


def delete(db: Session, record: FileRecord) -> None:
    db.delete(record)
    db.commit()
