import secrets

ALPHABET: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE: int = len(ALPHABET)
_INDEX: dict[str, int] = {c: i for i, c in enumerate(ALPHABET)}


def encode(n: int) -> str:
    if n < 0:
        raise ValueError("Value cannot be negative")
    elif n == 0:
        return ALPHABET[0]

    lst = []
    while n > 0:
        lst.append(ALPHABET[n % BASE])
        n = n // BASE

    return "".join(reversed(lst))


def decode(s: str) -> int:
    if not s:
        raise ValueError("string cannot be empty")
    value = 0
    for ch in s:
        try:
            value = value * BASE + _INDEX[ch]
        except KeyError:
            raise ValueError(f"{ch!r} is not a base62 character") from None

    return value


def random_key(length: int = 7) -> str:

    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_key(s: str, length: int) -> bool:
    return len(s) == length and all(ch in _INDEX for ch in s)
