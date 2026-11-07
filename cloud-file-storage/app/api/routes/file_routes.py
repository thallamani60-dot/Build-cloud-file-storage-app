from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import APIError
from app.core.limiter import limiter
from app.database.session import get_db
from app.models import User
from app.schemas.files import FileListResponse, FileRead, PresignedURLResponse
from app.services import file_service


router = APIRouter()
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]


@router.post("/upload", response_model=FileRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def upload(
    request: Request,
    user: CurrentUser,
    db: Database,
    file: UploadFile = File(...),
):
    body = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    return file_service.upload_file(
        db,
        owner_id=user.id,
        filename=file.filename,
        content_type=file.content_type,
        body=body,
    )


@router.get("", response_model=FileListResponse)
@router.get("/", response_model=FileListResponse, include_in_schema=False)
@limiter.limit("60/minute")
def list_files(
    request: Request,
    user: CurrentUser,
    db: Database,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    extension: str | None = Query(default=None, max_length=10),
    created_from: AwareDatetime | None = None,
    created_to: AwareDatetime | None = None,
):
    normalized_extension = extension.strip().lower() if extension else None
    if normalized_extension and not normalized_extension.startswith("."):
        normalized_extension = f".{normalized_extension}"
    if normalized_extension and normalized_extension not in settings.allowed_extensions:
        raise APIError(400, "invalid_extension_filter", "Extension filter is not supported")
    if created_from and created_to and created_from > created_to:
        raise APIError(400, "invalid_date_range", "created_from must not be later than created_to")
    items, total = file_service.list_files(
        db,
        user.id,
        limit=limit,
        offset=offset,
        query=q,
        extension=normalized_extension,
        created_from=created_from,
        created_to=created_to,
    )
    return FileListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{file_id}", response_model=FileRead)
@limiter.limit("60/minute")
def get_file(request: Request, file_id: UUID, user: CurrentUser, db: Database):
    return file_service.get_file(db, str(file_id), user.id)


@router.get("/{file_id}/download")
@limiter.limit("60/minute")
def download_file(request: Request, file_id: UUID, user: CurrentUser, db: Database) -> StreamingResponse:
    return file_service.download_file(db, str(file_id), user.id)


@router.get("/{file_id}/presigned-url", response_model=PresignedURLResponse)
@limiter.limit("60/minute")
def presigned_url(request: Request, file_id: UUID, user: CurrentUser, db: Database):
    return PresignedURLResponse(
        url=file_service.get_presigned_url(db, str(file_id), user.id),
        expires_in=settings.presigned_url_expire_seconds,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
def delete_file(request: Request, file_id: UUID, user: CurrentUser, db: Database):
    file_service.delete_file(db, str(file_id), user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
