from datetime import UTC, datetime, timedelta

import pytest

from app.models import Url
from app.services.urls import is_gone

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=1)


def make_url(*, expires_at=None, deleted_at=None) -> Url:
    return Url(
        short_id="aB3xY7z",
        long_url="https://example.com/",
        expires_at=expires_at,
        deleted_at=deleted_at,
    )


def test_live_url_without_expiry_is_not_gone():
    assert is_gone(make_url(), now=NOW) is False


def test_url_expiring_in_the_future_is_not_gone():
    assert is_gone(make_url(expires_at=FUTURE), now=NOW) is False


def test_expired_url_is_gone():
    assert is_gone(make_url(expires_at=PAST), now=NOW) is True


def test_expiry_boundary_is_inclusive():
    just_after = NOW + timedelta(microseconds=1)
    assert is_gone(make_url(expires_at=NOW), now=NOW) is True
    assert is_gone(make_url(expires_at=just_after), now=NOW) is False


def test_deleted_url_is_gone():
    assert is_gone(make_url(deleted_at=PAST), now=NOW) is True


def test_deleted_url_is_gone_even_when_expiry_is_in_the_future():
    assert is_gone(make_url(expires_at=FUTURE, deleted_at=PAST), now=NOW) is True


def test_deleted_and_expired_url_is_gone():
    assert is_gone(make_url(expires_at=PAST, deleted_at=PAST), now=NOW) is True


def test_deletion_timestamp_in_the_future_still_counts_as_deleted():
    assert is_gone(make_url(deleted_at=FUTURE), now=NOW) is True


@pytest.mark.parametrize(
    ("now", "expected"),
    [(PAST, False), (FUTURE, True)],
)
def test_now_argument_controls_the_verdict(now, expected):
    assert is_gone(make_url(expires_at=NOW), now=now) is expected


def test_now_defaults_to_current_time():
    assert is_gone(make_url(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert not is_gone(make_url(expires_at=datetime.now(UTC) + timedelta(hours=1)))


def test_naive_expiry_raises_rather_than_comparing_wrongly():
    with pytest.raises(TypeError):
        is_gone(make_url(expires_at=datetime(2026, 1, 1, 12, 0, 0)), now=NOW)


def test_is_gone_does_not_mutate_the_url():
    url = make_url(expires_at=FUTURE)
    is_gone(url, now=NOW)
    assert url.expires_at == FUTURE
    assert url.deleted_at is None
