from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.db import SessionDep
from app.schemas import ShortenRequest, ShortenResponse
from app.services.urls import KeyGenerationError, create_short_url

router = APIRouter(prefix="/api/urls", tags=["urls"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def shorten(
    payload: ShortenRequest, session: SessionDep, settings: SettingsDep
) -> ShortenResponse:
    try:
        url = await create_short_url(
            session,
            payload.long_url,
            settings=settings,
            expires_at=payload.expires_at,
        )
    except KeyGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not allocate a short id",
        ) from exc

    return ShortenResponse(
        short_id=url.short_id,
        short_url=f"{settings.base_url.rstrip('/')}/{url.short_id}",
    )
