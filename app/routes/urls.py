from fastapi import APIRouter, HTTPException, status

from app.config import SettingsDep
from app.db import SessionDep
from app.schemas import ShortenRequest, ShortenResponse, UrlMetadata
from app.services.urls import KeyGenerationError, create_short_url, get_url

router = APIRouter(prefix="/api/urls", tags=["urls"])


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


@router.get("/{short_id}", status_code=status.HTTP_200_OK)
async def get_url_metadata(short_id: str, session: SessionDep) -> UrlMetadata:
    url = await get_url(session, short_id)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="short url does not exist"
        )

    return UrlMetadata.model_validate(url)
