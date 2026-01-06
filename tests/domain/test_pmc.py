import pytest

from coda.domain.publication.links import Pmc


def test_can_create_pmc() -> None:
    sut = Pmc("PMC3531190")

    assert str(sut) == "PMC3531190"
    assert sut.value() == "PMC3531190"


def test_pmc_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Pmc(" PMC8876543 ")

    assert str(sut) == "PMC8876543"


@pytest.mark.parametrize(
    "valid_pmc",
    [
        "PMC12345",
        "PMC123456",
        "PMC1234567",
        "PMC3531190",
        "PMC8876543",
        "pmc3531190",
        "Pmc123456",
    ],
)
def test_valid_pmc_formats(valid_pmc: str) -> None:
    sut = Pmc(valid_pmc)
    assert str(sut).startswith("PMC")
    assert str(sut)[3:].isdigit()


@pytest.mark.parametrize(
    "invalid_pmc",
    [
        "",
        " ",
        "123456",
        "PMC",
        "PMC-123456",
        "PMC 123456",
        "PMCabc123",
        "PMID123456",
        "PC123456",
    ],
)
def test_invalid_pmc_formats(invalid_pmc: str) -> None:
    with pytest.raises(ValueError):
        Pmc(invalid_pmc)


def test_pmc_url_returns_pubmed_central_url() -> None:
    sut = Pmc("PMC3531190")

    assert sut.url() == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3531190/"


def test_pmc_normalizes_to_uppercase() -> None:
    sut = Pmc("pmc3531190")

    assert str(sut) == "PMC3531190"
