from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from app.cache import RedisDep
from app.config import SettingsDep
from app.db import SessionDep
from app.services.urls import Resolution, resolve_short_id
from app.utils.base62 import is_valid_key

router = APIRouter(tags=["redirect"])


@router.get(
    "/{short_id}", status_code=status.HTTP_302_FOUND, response_class=RedirectResponse
)
async def redirect(
    short_id: str, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> RedirectResponse:

    if not is_valid_key(short_id, settings.short_id_length):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="short url does not exist"
        )

    resolution, long_url = await resolve_short_id(
        session, redis, short_id, settings=settings
    )
    match resolution:
        case Resolution.FOUND:
            return RedirectResponse(
                url=long_url,
                status_code=status.HTTP_302_FOUND,
                headers={"Cache-Control": "no-store"},
            )
        case Resolution.GONE:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="The url is deleted or expired",
            )
        case _:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="short url does not exist",
            )
