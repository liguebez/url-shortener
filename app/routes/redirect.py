from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from app.config import SettingsDep
from app.db import SessionDep
from app.services.urls import get_url, is_gone
from app.utils.base62 import is_valid_key

router = APIRouter(tags=["redirect"])


@router.get(
    "/{short_id}", status_code=status.HTTP_302_FOUND, response_class=RedirectResponse
)
async def redirect(
    short_id: str, session: SessionDep, settings: SettingsDep
) -> RedirectResponse:

    if not is_valid_key(short_id, settings.short_id_length):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="short url does not exist"
        )

    url = await get_url(session, short_id)
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="short url does not exist"
        )
    if is_gone(url):
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="The url is deleted or expired"
        )

    return RedirectResponse(
        url=url.long_url,
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store"},
    )
