from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import Url

LONG_URL = "https://example.com/target"


async def test_shorten_returns_201(client):
    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    assert response.status_code == 201


async def test_shorten_returns_a_seven_character_base62_id(client):
    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    short_id = response.json()["short_id"]
    assert len(short_id) == 7
    assert short_id.isalnum()


async def test_short_url_is_built_from_the_configured_base_url(client):
    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    body = response.json()
    base = get_settings().base_url.rstrip("/")
    assert body["short_url"] == f"{base}/{body['short_id']}"


async def test_shorten_persists_the_row(client, session):
    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    url = await session.get(Url, response.json()["short_id"])
    assert url is not None
    assert url.long_url == LONG_URL


async def test_created_row_has_no_expiry_by_default(client, session):
    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    url = await session.get(Url, response.json()["short_id"])
    assert url.expires_at is None
    assert url.deleted_at is None


async def test_the_same_long_url_gets_two_distinct_short_ids(client):
    first = await client.post("/api/urls", json={"long_url": LONG_URL})
    second = await client.post("/api/urls", json={"long_url": LONG_URL})
    assert first.json()["short_id"] != second.json()["short_id"]


async def test_expires_at_is_stored(client, session):
    expiry = datetime.now(UTC) + timedelta(days=7)
    response = await client.post(
        "/api/urls",
        json={"long_url": LONG_URL, "expires_at": expiry.isoformat()},
    )
    url = await session.get(Url, response.json()["short_id"])
    assert url.expires_at == expiry


@pytest.mark.parametrize(
    "long_url",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "example.com",
        "not a url",
        "",
        "http://localhost/x",
        "http://127.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://svc.internal/",
        "https://user:pass@example.com/",
    ],
)
async def test_rejected_urls_return_400(client, long_url):
    response = await client.post("/api/urls", json={"long_url": long_url})
    assert response.status_code == 400


async def test_a_url_over_the_length_cap_returns_400(client):
    too_long = "https://example.com/" + "a" * get_settings().max_url_length
    response = await client.post("/api/urls", json={"long_url": too_long})
    assert response.status_code == 400


async def test_a_missing_body_field_returns_400(client):
    response = await client.post("/api/urls", json={})
    assert response.status_code == 400


async def test_a_validation_failure_carries_a_detail(client):
    response = await client.post("/api/urls", json={"long_url": "not a url"})
    assert response.json()["detail"]


async def test_nothing_is_persisted_for_a_rejected_url(client, session):
    await client.post("/api/urls", json={"long_url": "javascript:alert(1)"})
    result = await session.execute(Url.__table__.select())
    assert result.first() is None


async def test_exhausted_key_space_returns_503(client, session, monkeypatch):
    session.add(Url(short_id="AAAAAAA", long_url=LONG_URL))
    await session.flush()
    monkeypatch.setattr("app.services.urls.random_key", lambda length: "AAAAAAA")

    response = await client.post("/api/urls", json={"long_url": LONG_URL})
    assert response.status_code == 503


async def test_metadata_returns_the_stored_record(client):
    created = await client.post("/api/urls", json={"long_url": LONG_URL})
    short_id = created.json()["short_id"]

    response = await client.get(f"/api/urls/{short_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["short_id"] == short_id
    assert body["long_url"] == LONG_URL
    assert body["created_at"]
    assert body["expires_at"] is None
    assert body["deleted_at"] is None


async def test_metadata_returns_404_for_an_unknown_id(client):
    response = await client.get("/api/urls/zzzzzzz")
    assert response.status_code == 404


async def test_metadata_still_describes_an_expired_url(client, session):
    expiry = datetime.now(UTC) - timedelta(days=1)
    session.add(Url(short_id="aB3xY7z", long_url=LONG_URL, expires_at=expiry))
    await session.flush()

    response = await client.get("/api/urls/aB3xY7z")
    assert response.status_code == 200
    assert response.json()["expires_at"]


async def test_metadata_still_describes_a_deleted_url(client, session):
    session.add(
        Url(short_id="aB3xY7z", long_url=LONG_URL, deleted_at=datetime.now(UTC))
    )
    await session.flush()

    response = await client.get("/api/urls/aB3xY7z")
    assert response.status_code == 200
    assert response.json()["deleted_at"]
