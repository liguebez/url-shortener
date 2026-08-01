from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ShortenRequest(BaseModel):
    long_url: str
    expires_at: datetime | None = None


class ShortenResponse(BaseModel):
    short_id: str
    short_url: str


class UrlMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    short_id: str
    long_url: str
    created_at: datetime
    expires_at: datetime | None
    deleted_at: datetime | None
