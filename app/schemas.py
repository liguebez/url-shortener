from datetime import datetime

from pydantic import BaseModel


class ShortenRequest(BaseModel):
    long_url: str
    expires_at: datetime | None = None


class ShortenResponse(BaseModel):
    short_id: str
    short_url: str
