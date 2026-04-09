import pytest

from coda.domain.institution.links import Isni, Ringgold, Ror


def test__can_create_valid_ror() -> None:
    """ROR format: https://ror.org/0xxxxxx (9 characters after last slash)."""
    sut = Ror("https://ror.org/02mhbdp94")

    assert str(sut) == "https://ror.org/02mhbdp94"
    assert sut.value() == "https://ror.org/02mhbdp94"


def test__ror_with_leading_or_trailing_whitespace__get_trimmed() -> None:
    sut = Ror(" https://ror.org/02mhbdp94 ")
    assert str(sut) == "https://ror.org/02mhbdp94"


def test__ror_with_invalid_checksum__raises_error() -> None:
    # Valid: https://ror.org/02mhbdp94 (checksum 94)
    # Invalid: change checksum to 95 (wrong checksum)
    with pytest.raises(ValueError):
        Ror("https://ror.org/02mhbdp95")


@pytest.mark.parametrize(
    "invalid_ror",
    [
        "",
        " ",
        "https://ror.org/",
        "https://ror.org/123",
        "https://ror.org/0123456789",
        "http://ror.org/02mhbdp94",
        "ror.org/02mhbdp94",
        "02mhbdp94",
        "https://ror.com/02mhbdp94",
    ],
)
def test__invalid_ror_formats__raise_error(invalid_ror: str) -> None:
    with pytest.raises(ValueError):
        Ror(invalid_ror)


@pytest.mark.parametrize(
    "valid_ror",
    [
        "https://ror.org/02mhbdp94",
        "https://ror.org/05dxps055",
        "https://ror.org/04cvxnb49",
    ],
)
def test_valid_ror_formats(valid_ror: str) -> None:
    sut = Ror(valid_ror)
    assert str(sut) == valid_ror


def test_can_create_valid_isni() -> None:
    """ISNI format: 16 digits, often formatted as 0000 0001 2345 6789."""
    sut = Isni("0000000121032683")

    assert str(sut) == "0000000121032683"
    assert sut.value() == "0000000121032683"


@pytest.mark.parametrize(
    "valid_isni",
    [
        "0000000121032683",
        "0000 0001 2103 2683",
        "0000-0001-2103-2683",
        "0000 0001 2345 678X",
    ],
)
def test_valid_isni_formats(valid_isni: str) -> None:
    sut = Isni(valid_isni)
    expected = valid_isni.replace(" ", "").replace("-", "")
    assert str(sut) == expected


@pytest.mark.parametrize(
    "invalid_isni",
    [
        "",
        " ",
        "123",
        "12345678901234567",
        "000000012103268A",
        "ABCD0001210326AB",
    ],
)
def test_invalid_isni_formats(invalid_isni: str) -> None:
    with pytest.raises(ValueError):
        Isni(invalid_isni)


def test_isni_with_whitespace_gets_trimmed() -> None:
    sut = Isni(" 0000000121032683 ")
    assert str(sut) == "0000000121032683"


def test_isni_formatting_is_normalized() -> None:
    sut = Isni("0000 0001 2103 2683")
    assert str(sut) == "0000000121032683"


def test_can_create_valid_ringold() -> None:
    """Ringgold format: numeric identifier."""
    sut = Ringgold("12345")

    assert str(sut) == "12345"
    assert sut.value() == "12345"


@pytest.mark.parametrize(
    "valid_ringold",
    [
        "12345",
        "123456",
        "1234567",
    ],
)
def test_valid_ringold_formats(valid_ringold: str) -> None:
    sut = Ringgold(valid_ringold)
    assert str(sut) == valid_ringold


@pytest.mark.parametrize(
    "invalid_ringold",
    [
        "",
        " ",
        "ABC123",
        "123-456",
        "123.456",
    ],
)
def test_invalid_ringold_formats(invalid_ringold: str) -> None:
    with pytest.raises(ValueError):
        Ringgold(invalid_ringold)


def test_ringold_with_whitespace_gets_trimmed() -> None:
    sut = Ringgold(" 12345 ")
    assert str(sut) == "12345"
