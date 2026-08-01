import pytest

from app.utils.validation import is_blocked_host, validate_long_url

MAX_LENGTH = 2048
PREFIX = "https://example.com/"


def url_of_length(length: int) -> str:
    return PREFIX + "a" * (length - len(PREFIX))


ACCEPTED = [
    "https://example.com",
    "https://example.com/",
    "https://example.com/a/b/c?q=1&r=2#frag",
    "http://example.com:8080/path",
    "https://sub.domain.example.co.uk/x",
    "https://example.com/notes/my.local/readme.txt",
    "https://example.com/?redirect=http://localhost/x",
    "http://8.8.8.8/",
    "http://[2606:4700:4700::1111]/",
    "https://localhost.example.com/",
    "https://notlocalhost/",
]

REJECTED = [
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "//example.com/x",
    "example.com",
    "not a url",
    "",
    "http:///path",
    "http://localhost/x",
    "http://localhost:3000/",
    "http://foo.localhost/",
    "http://printer.local/",
    "http://svc.internal/",
    "http://127.0.0.1/",
    "http://127.0.0.1:5432/",
    "http://10.0.0.1/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://[fd00::1]/",
    "http://[fe80::1]/",
    "http://[::ffff:127.0.0.1]/",
    "https://evil.com@127.0.0.1/",
    "https://user:pass@example.com/",
]


@pytest.mark.parametrize("url", ACCEPTED)
def test_accepted_urls_pass_through_unchanged(url):
    assert validate_long_url(url, max_length=MAX_LENGTH) == url


@pytest.mark.parametrize("url", REJECTED)
def test_rejected_urls_raise_value_error(url):
    with pytest.raises(ValueError):
        validate_long_url(url, max_length=MAX_LENGTH)


@pytest.mark.parametrize("url", REJECTED)
def test_every_rejection_carries_a_message(url):
    with pytest.raises(ValueError) as excinfo:
        validate_long_url(url, max_length=MAX_LENGTH)
    assert str(excinfo.value).strip()


def test_scheme_comparison_is_case_insensitive():
    assert validate_long_url("HtTpS://Example.COM/x", max_length=MAX_LENGTH)


def test_surrounding_whitespace_is_stripped():
    assert validate_long_url("  https://example.com/x\n", max_length=MAX_LENGTH) == (
        "https://example.com/x"
    )


def test_whitespace_is_stripped_before_the_length_check():
    padded = "  " + url_of_length(MAX_LENGTH) + "  "
    assert validate_long_url(padded, max_length=MAX_LENGTH) == url_of_length(MAX_LENGTH)


def test_length_boundary_is_inclusive():
    assert validate_long_url(url_of_length(MAX_LENGTH), max_length=MAX_LENGTH)
    with pytest.raises(ValueError, match="long"):
        validate_long_url(url_of_length(MAX_LENGTH + 1), max_length=MAX_LENGTH)


def test_length_limit_is_taken_from_the_argument():
    url = url_of_length(64)
    assert validate_long_url(url, max_length=64)
    with pytest.raises(ValueError, match="long"):
        validate_long_url(url, max_length=63)


def test_credentials_are_rejected_before_the_host_is_checked():
    with pytest.raises(ValueError, match="credentials"):
        validate_long_url("https://evil.com@example.com/", max_length=MAX_LENGTH)


def test_uppercase_host_is_normalized_before_blocking():
    with pytest.raises(ValueError, match="host"):
        validate_long_url("http://LOCALHOST/x", max_length=MAX_LENGTH)


BLOCKED_IPS = [
    "127.0.0.1",
    "127.1.2.3",
    "10.0.0.1",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",
    "0.0.0.0",
    "224.0.0.1",
    "255.255.255.255",
    "::1",
    "fd00::1",
    "fe80::1",
    "::",
    "::ffff:127.0.0.1",
    "::ffff:192.168.1.1",
]

ALLOWED_IPS = [
    "8.8.8.8",
    "1.1.1.1",
    "93.184.216.34",
    "2606:4700:4700::1111",
]

BLOCKED_NAMES = [
    "localhost",
    "foo.localhost",
    "deeply.nested.localhost",
    "printer.local",
    "svc.internal",
    "a.b.c.internal",
]

ALLOWED_NAMES = [
    "example.com",
    "sub.example.com",
    "localhost.example.com",
    "notlocalhost",
    "local",
    "internal",
    "my.locality.example.com",
]


@pytest.mark.parametrize("host", BLOCKED_IPS)
def test_is_blocked_host_blocks_non_public_addresses(host):
    assert is_blocked_host(host) is True


@pytest.mark.parametrize("host", ALLOWED_IPS)
def test_is_blocked_host_allows_public_addresses(host):
    assert is_blocked_host(host) is False


@pytest.mark.parametrize("host", BLOCKED_NAMES)
def test_is_blocked_host_blocks_local_names(host):
    assert is_blocked_host(host) is True


@pytest.mark.parametrize("host", ALLOWED_NAMES)
def test_is_blocked_host_allows_public_names(host):
    assert is_blocked_host(host) is False


@pytest.mark.parametrize(
    ("mapped", "plain"),
    [("::ffff:127.0.0.1", "127.0.0.1"), ("::ffff:192.168.1.1", "192.168.1.1")],
)
def test_ipv4_mapped_ipv6_matches_the_address_it_maps(mapped, plain):
    assert is_blocked_host(mapped) is is_blocked_host(plain) is True


@pytest.mark.parametrize("host", ["2130706433", "0177.0.0.1", "0x7f.1"])
def test_known_gap_alternate_ip_encodings_are_not_blocked(host):
    assert is_blocked_host(host) is False


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0177.0.0.1/"])
def test_known_gap_alternate_ip_encodings_are_accepted(url):
    assert validate_long_url(url, max_length=MAX_LENGTH) == url
