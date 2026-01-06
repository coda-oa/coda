import pytest

from coda.domain.publication.links import Pmid


def test_can_create_pmid() -> None:
    sut = Pmid("12345678")

    assert str(sut) == "12345678"
    assert sut.value() == "12345678"


def test_pmid_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Pmid(" 38234156 ")

    assert str(sut) == "38234156"


@pytest.mark.parametrize(
    "valid_pmid",
    [
        "12345",
        "123456",
        "1234567",
        "12345678",
        "123456789",
    ],
)
def test_valid_pmid_formats(valid_pmid: str) -> None:
    sut = Pmid(valid_pmid)
    assert str(sut) == valid_pmid


@pytest.mark.parametrize(
    "invalid_pmid",
    [
        "",
        " ",
        "ABC123",
        "123-456",
        "123.456",
        "12345abc",
        "PMID12345",
        "PMC123456",
    ],
)
def test_invalid_pmid_formats(invalid_pmid: str) -> None:
    with pytest.raises(ValueError):
        Pmid(invalid_pmid)


def test_pmid_url_returns_pubmed_url() -> None:
    sut = Pmid("12345678")

    assert sut.url() == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
