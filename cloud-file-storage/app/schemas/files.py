from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class FileListResponse(BaseModel):
    items: list[FileRead]
    total: int
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PresignedURLResponse(BaseModel):
    url: str
    expires_in: int
