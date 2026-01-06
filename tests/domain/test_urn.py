import pytest

from coda.domain.publication.links import Urn


def test_can_create_urn() -> None:
    sut = Urn("urn:isbn:0451450523")

    assert str(sut) == "urn:isbn:0451450523"
    assert sut.value() == "urn:isbn:0451450523"


def test_urn_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Urn(" urn:issn:1234-5678 ")

    assert str(sut) == "urn:issn:1234-5678"


@pytest.mark.parametrize(
    "valid_urn",
    [
        "urn:isbn:0451450523",
        "urn:issn:1234-5678",
        "urn:ietf:rfc:2648",
        "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66",
        "urn:nbn:de:bsz:291-scidok-12345",
        "URN:ISBN:0451450523",
        "urn:ISBN:0451450523",
    ],
)
def test_valid_urn_formats(valid_urn: str) -> None:
    sut = Urn(valid_urn)
    assert str(sut).lower() == str(sut)
    assert str(sut).startswith("urn:")


@pytest.mark.parametrize(
    "invalid_urn",
    [
        "",
        " ",
        "isbn:0451450523",
        "urn:",
        "urn:isbn",
        "urn:isbn:",
        "not-a-urn",
        "urn",
    ],
)
def test_invalid_urn_formats(invalid_urn: str) -> None:
    with pytest.raises(ValueError):
        Urn(invalid_urn)


def test_urn_normalizes_to_lowercase() -> None:
    sut = Urn("URN:ISBN:0451450523")

    assert str(sut) == "urn:isbn:0451450523"


def test_urn_url_returns_none() -> None:
    sut = Urn("urn:isbn:0451450523")

    assert sut.url() is None
