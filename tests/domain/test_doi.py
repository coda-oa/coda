import pytest

from coda.doi import Doi


def test_can_create_doi() -> None:
    sut = Doi("10.1234/foobar")

    assert str(sut) == "10.1234/foobar"
    assert sut.prefix == "10.1234"
    assert sut.suffix == "foobar"


def test__dois_with_leading_or_trailing_whitespace__get_trimmed() -> None:
    sut = Doi(" 10.1234/foobar ")

    assert str(sut) == "10.1234/foobar"
    assert sut.prefix == "10.1234"
    assert sut.suffix == "foobar"


@pytest.mark.parametrize(
    "invalid_doi",
    ["", " ", "10.1234", "10.1234/", "/foobar"],
)
def test__doi_requires_prefix_and_suffix(invalid_doi: str) -> None:
    with pytest.raises(ValueError):
        Doi(invalid_doi)


@pytest.mark.parametrize(
    "invalid_doi",
    ["11.1234/foobar", "9.1234/foobar", ".1234/foobar", "100.1234/foobar"],
)
def test__doi_prefix_must_start_with_10_point(invalid_doi: str) -> None:
    with pytest.raises(ValueError):
        Doi(invalid_doi)


def test__doi__url__returns_url() -> None:
    sut = Doi("10.1234/foobar")

    assert sut.url == f"https://doi.org/{sut}"
