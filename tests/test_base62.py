import random
import secrets

import pytest

from app.utils.base62 import (
    ALPHABET,
    BASE,
    decode,
    encode,
    is_valid_key,
    random_key,
)

ANCHORS = [
    (0, "0"),
    (1, "1"),
    (61, "z"),
    (62, "10"),
    (124, "20"),
    (3843, "zz"),
    (3844, "100"),
    (3849, "105"),
    (BASE**7 - 1, "zzzzzzz"),
]


def test_alphabet_is_62_distinct_characters():
    assert BASE == 62
    assert len(ALPHABET) == 62
    assert len(set(ALPHABET)) == 62


def test_index_matches_alphabet_order():
    assert [decode(char) for char in ALPHABET] == list(range(BASE))


@pytest.mark.parametrize(("number", "text"), ANCHORS)
def test_encode_anchors(number, text):
    assert encode(number) == text


@pytest.mark.parametrize(("number", "text"), ANCHORS)
def test_decode_anchors(number, text):
    assert decode(text) == number


@pytest.mark.parametrize(
    "number", [0, 1, 61, 62, 3843, 3844, 3849, BASE**7 - 1, BASE**8]
)
def test_roundtrip_fixed(number):
    assert decode(encode(number)) == number


def test_roundtrip_random_sample():
    for _ in range(500):
        number = secrets.randbelow(BASE**7)
        assert decode(encode(number)) == number


def test_encode_rejects_negative():
    with pytest.raises(ValueError, match="negative"):
        encode(-1)


def test_decode_rejects_empty_string():
    with pytest.raises(ValueError, match="empty"):
        decode("")


@pytest.mark.parametrize(
    "text",
    ["abc!", "é", "aa aa", "٨", chr(0xFF10), "-", "a/b", " 1", "1 ", "\t"],
)
def test_decode_rejects_non_base62(text):
    with pytest.raises(ValueError, match="base62"):
        decode(text)


def test_decode_ignores_leading_zeros():
    assert decode("01") == decode("1") == 1
    assert decode("0000105") == decode("105")


def test_random_key_default_length_is_seven():
    assert len(random_key()) == 7


@pytest.mark.parametrize("length", [1, 7, 10, 22])
def test_random_key_honors_length(length):
    assert len(random_key(length)) == length


def test_random_key_sample_is_well_formed():
    keys = [random_key() for _ in range(1000)]
    assert all(len(key) == 7 for key in keys)
    assert all(char in ALPHABET for key in keys for char in key)
    assert len(set(keys)) == 1000


def test_random_key_covers_whole_alphabet():
    seen = {char for _ in range(2000) for char in random_key()}
    assert seen == set(ALPHABET)


def test_random_key_is_unaffected_by_seeding_stdlib_random():
    random.seed(0)
    first = random_key()
    random.seed(0)
    second = random_key()
    assert first != second


@pytest.mark.parametrize("text", ["0000000", "zzzzzzz", "aB3xY7z", "0123456"])
def test_is_valid_key_accepts_well_formed_keys(text):
    assert is_valid_key(text, 7) is True


def test_is_valid_key_accepts_every_alphabet_character():
    assert all(is_valid_key(char, 1) for char in ALPHABET)


@pytest.mark.parametrize("length", [1, 7, 10, 22])
def test_is_valid_key_accepts_random_key_output(length):
    assert is_valid_key(random_key(length), length)


@pytest.mark.parametrize("text", ["", "abc", "abcdef", "abcdefgh", "a" * 64])
def test_is_valid_key_rejects_wrong_length(text):
    assert is_valid_key(text, 7) is False


@pytest.mark.parametrize(
    "text",
    ["abcdef!", "abcde-f", "abcde_f", "abcd/ef", "abcde f", "abcdef\t", "abcdeéf"],
)
def test_is_valid_key_rejects_non_base62_characters(text):
    assert is_valid_key(text, 7) is False


@pytest.mark.parametrize(
    "text",
    [
        "\u0661\u0662\u0663\u0664\u0665\u0666\u0667",
        "\uff11\uff12\uff13\uff14\uff15\uff16\uff17",
    ],
)
def test_is_valid_key_rejects_non_ascii_digits(text):
    assert is_valid_key(text, 7) is False


def test_is_valid_key_rejects_favicon_and_common_probe_paths():
    for text in ["favicon.ico", "robots.txt", "index.php", "wp-admin", ".env"]:
        assert is_valid_key(text, 7) is False


def test_is_valid_key_length_is_exact_not_minimum():
    assert is_valid_key("aaaaaaa", 7) is True
    assert is_valid_key("aaaaaaa", 6) is False
    assert is_valid_key("aaaaaaa", 8) is False
