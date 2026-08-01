from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.config import get_settings
from app.utils.validation import validate_long_url


class ShortenRequest(BaseModel):
    long_url: str
    expires_at: datetime | None = None

    @field_validator("long_url")
    @classmethod
    def check_long_url(cls, v: str) -> str:
        return validate_long_url(v, max_length=get_settings().max_url_length)


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
