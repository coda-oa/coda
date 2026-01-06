import re
from typing import Any

from coda.domain.errors import DomainError
from coda.domain.string import NonEmptyStr


def _decode_base32_crockford(encoded: str) -> int:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    encoded = encoded.upper()

    result = 0
    for char in encoded:
        if char not in alphabet:
            raise ValueError(f"Invalid base32-crockford character: {char}")
        result = result * 32 + alphabet.index(char)

    return result


class InvalidRor(DomainError):
    def __init__(self, message: str = "Invalid ROR format", *args: object) -> None:
        super().__init__(message, *args)


class InvalidIsni(DomainError):
    def __init__(self, message: str = "Invalid ISNI format", *args: object) -> None:
        super().__init__(message, *args)


class InvalidRinggold(DomainError):
    def __init__(self, message: str = "Invalid Ringgold format", *args: object) -> None:
        super().__init__(message, *args)


class Ror:
    __match_args__ = ("_ror",)

    def __init__(self, ror: str) -> None:
        self._ror = NonEmptyStr(ror).strip()
        error_message = self._validate()
        if error_message:
            raise InvalidRor(error_message)

    @staticmethod
    def type() -> str:
        return "ROR"

    def _validate(self) -> str | None:
        if not self._ror.startswith("https://ror.org/"):
            return "Invalid ROR format: must start with 'https://ror.org/'"

        ror_id = self._ror.split("/")[-1]

        pattern = r"^0[a-hj-km-np-tv-z\d]{6}\d{2}$"
        if not re.match(pattern, ror_id, re.IGNORECASE):
            return "Invalid ROR format: ID must be 0 + 6 base32 characters + 2 checksum digits"

        base32_part = ror_id[1:7]  # Skip the leading '0', take next 6 chars
        checksum_part = ror_id[7:9]  # Last 2 digits

        try:
            n = _decode_base32_crockford(base32_part)
            expected_checksum = str(98 - ((n * 100) % 97)).zfill(2)
            if checksum_part != expected_checksum:
                return f"Invalid ROR ID: checksum verification failed (expected {expected_checksum}, got {checksum_part})"
        except ValueError:
            return "Invalid ROR format: contains invalid base32 characters"

        return None

    def value(self) -> str:
        return self._ror

    def url(self) -> str:
        return self._ror

    def __str__(self) -> str:
        return self._ror

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Ror):
            return False
        return self._ror == other._ror

    def __hash__(self) -> int:
        return hash((self._ror,))


class Isni:
    __match_args__ = ("_isni",)

    def __init__(self, isni: str) -> None:
        normalized = NonEmptyStr(isni).strip().replace(" ", "").replace("-", "")
        self._isni = normalized.upper()
        error_message = self._validate()
        if error_message:
            raise InvalidIsni(error_message)

    @staticmethod
    def type() -> str:
        return "ISNI"

    def _validate(self) -> str | None:
        pattern = r"^\d{15}[\dX]$"
        if not re.match(pattern, self._isni):
            return "Invalid ISNI format: must be 16 characters (15 digits + check digit 0-9 or X)"

        return None

    def value(self) -> str:
        return self._isni

    def __str__(self) -> str:
        return self._isni

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Isni):
            return False
        return self._isni == other._isni

    def __hash__(self) -> int:
        return hash((self._isni,))


class Ringgold:
    __match_args__ = ("_ringgold",)

    def __init__(self, ringgold: str) -> None:
        self._ringgold = NonEmptyStr(ringgold).strip()
        error_message = self._validate()
        if error_message:
            raise InvalidRinggold(error_message)

    @staticmethod
    def type() -> str:
        return "Ringgold"

    def _validate(self) -> str | None:
        if not self._ringgold.isdigit():
            return "Invalid Ringgold format: must contain only digits"
        return None

    def value(self) -> str:
        return self._ringgold

    def __str__(self) -> str:
        return self._ringgold

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Ringgold):
            return False
        return self._ringgold == other._ringgold

    def __hash__(self) -> int:
        return hash((self._ringgold,))
