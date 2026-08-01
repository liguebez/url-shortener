import ipaddress
from urllib.parse import urlsplit

ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
BLOCKED_SUFFIXES: tuple[str, ...] = (".localhost", ".local", ".internal")


def validate_long_url(raw: str, *, max_length: int) -> str:

    raw = raw.strip()

    if len(raw) > max_length:
        raise ValueError("the url is too long")

    parsed = urlsplit(raw)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError("the scheme of url is wrong")

    if parsed.hostname is None:
        raise ValueError("the hostname should not be empty")

    if parsed.username or parsed.password:
        raise ValueError("url must not contain credentials")

    if is_blocked_host(parsed.hostname):
        raise ValueError("url host is not allowed")

    return raw


def is_blocked_host(host: str) -> bool:

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost" or host.endswith(BLOCKED_SUFFIXES)

    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
