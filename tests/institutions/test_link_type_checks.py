import pytest

from coda.domain.institution.links import Ror


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


# ISNI (International Standard Name Identifier) Tests


def test_can_create_valid_isni() -> None:
    """ISNI format: 16 digits, often formatted as 0000 0001 2345 6789."""
    pytest.skip("ISNI validation not yet implemented")


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
    pytest.skip("ISNI validation not yet implemented")


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
    pytest.skip("ISNI validation not yet implemented")


def test_isni_with_whitespace_gets_trimmed() -> None:
    pytest.skip("ISNI validation not yet implemented")


def test_isni_formatting_is_normalized() -> None:
    """Test that ISNI stores the normalized format (no spaces/dashes)."""
    pytest.skip("ISNI validation not yet implemented")


# Ringold Tests


def test_can_create_valid_ringold() -> None:
    """Ringold format: numeric identifier."""
    pytest.skip("Ringold validation not yet implemented")


@pytest.mark.parametrize(
    "valid_ringold",
    [
        "12345",
        "123456",
        "1234567",
    ],
)
def test_valid_ringold_formats(valid_ringold: str) -> None:
    pytest.skip("Ringold validation not yet implemented")


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
    pytest.skip("Ringold validation not yet implemented")


def test_ringold_with_whitespace_gets_trimmed() -> None:
    pytest.skip("Ringold validation not yet implemented")


# Handle Tests


def test_can_create_valid_handle() -> None:
    """Handle format: prefix/suffix pattern."""
    pytest.skip("Handle validation not yet implemented")


@pytest.mark.parametrize(
    "valid_handle",
    [
        "1234/5678",
        "10.1234/5678",
        "hdl:1234/5678",
        "https://hdl.handle.net/1234/5678",
    ],
)
def test_valid_handle_formats(valid_handle: str) -> None:
    pytest.skip("Handle validation not yet implemented")


@pytest.mark.parametrize(
    "invalid_handle",
    [
        "",
        " ",
        "1234",
        "/5678",
        "1234/",
    ],
)
def test_invalid_handle_formats(invalid_handle: str) -> None:
    pytest.skip("Handle validation not yet implemented")


def test_handle_with_whitespace_gets_trimmed() -> None:
    pytest.skip("Handle validation not yet implemented")
