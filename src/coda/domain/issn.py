from coda.domain.errors import DomainError


class InvalidIssn(DomainError):
    pass


class Issn(str):
    def __new__(cls, value: str) -> "Issn":
        return super().__new__(cls, canonical_issn(value))


def canonical_issn(value: str) -> str:
    """Canonical hyphenated ISSN for value.

    Accepts the canonical form, a bare 8-symbol ISSN (hyphen inserted) and a
    misplaced hyphen, then normalises to ``NNNN-NNNC``. The check character is
    uppercased.

    Raises:
        InvalidIssn: when value does not contain exactly eight ISSN symbols with a
            valid check character.
    """
    compact = value.strip().replace("-", "")
    if len(compact) != 8:
        raise InvalidIssn(f"ISSN must have 8 symbols, got {value!r}")

    digits, check = compact[:7], compact[7].upper()
    if not (digits.isascii() and digits.isdigit()):
        raise InvalidIssn(f"ISSN has non-digit characters: {value!r}")
    if check not in "0123456789X":
        raise InvalidIssn(f"ISSN has an invalid check character: {value!r}")

    canonical = f"{digits[:4]}-{digits[4:]}{check}"
    if checksum(canonical) != check:
        raise InvalidIssn(f"ISSN has invalid checksum: {value!r}")

    return canonical


def checksum(issn: str) -> str:
    """
    Calculate the checksum for an ISSN.
    For more details see:
    https://en.wikipedia.org/wiki/International_Standard_Serial_Number
    """
    issn = issn.replace("-", "")
    total = 0
    for i, digit in enumerate(issn[:7]):
        total += int(digit) * (8 - i)
    remainder = total % 11
    result = 0 if remainder == 0 else 11 - remainder
    return "X" if result == 10 else str(result)


def parse_issn(value: str) -> str | None:
    """Hyphenated ISSN for value, or None when value is not a canonical ISSN.

    Deliberately stricter than ``Issn`` for auto-detection: only the canonical
    hyphenated shape is claimed, so bare numeric tokens stay generic search terms.
    """
    if len(value) != 9 or value[4] != "-":
        return None
    try:
        return str(Issn(value))
    except ValueError:
        return None
