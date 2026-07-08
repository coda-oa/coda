import pytest

from coda.domain.publication.links import CrossrefId, InvalidCrossrefId


def test_can_create_crossref_id() -> None:
    sut = CrossrefId("100000014")

    assert str(sut) == "100000014"
    assert sut.value() == "100000014"
    assert sut.type() == "Crossref"


def test__crossref_id__url__returns_doi_url() -> None:
    sut = CrossrefId("100000014")

    assert sut.url() == "https://doi.org/10.13039/100000014"


@pytest.mark.parametrize(
    "invalid_value",
    ["abc", "10.13039/100000014", "doi:10.13039/100000014", "not-digits"],
)
def test__crossref_id__non_digit_value__raises_error(invalid_value: str) -> None:
    with pytest.raises(InvalidCrossrefId):
        CrossrefId(invalid_value)


@pytest.mark.parametrize("invalid_value", ["", " "])
def test__crossref_id__empty_or_blank__raises_value_error(invalid_value: str) -> None:
    with pytest.raises(ValueError):
        CrossrefId(invalid_value)


def test__crossref_id__equality() -> None:
    a = CrossrefId("100000014")
    b = CrossrefId("100000014")
    c = CrossrefId("501100002347")

    assert a == b
    assert a != c
    assert hash(a) == hash(b)


def test__crossref_id__can_be_created_via_create_link() -> None:
    from coda.domain.publication.links import create_link

    link = create_link("Crossref", "100000014")

    assert isinstance(link, CrossrefId)
    assert str(link) == "100000014"
