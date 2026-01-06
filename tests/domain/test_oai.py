import pytest

from coda.domain.oai import Oai


def test_can_create_oai() -> None:
    sut = Oai("oai:arXiv.org:hep-th/9901001")

    assert str(sut) == "oai:arXiv.org:hep-th/9901001"
    assert sut.value() == "oai:arXiv.org:hep-th/9901001"


def test_oai_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Oai(" oai:foo.org:some-local-id-53 ")

    assert str(sut) == "oai:foo.org:some-local-id-53"


@pytest.mark.parametrize(
    "valid_oai",
    [
        "oai:arXiv.org:hep-th/9901001",
        "oai:foo.org:some-local-id-53",
        "oai:FOO.ORG:some-local-id-53",
        "oai:wibble.org:ab%20cd",
        "oai:wibble.org:ab?cd",
        "oai:example.com:12345",
        "oai:sub.domain.org:xyz/123",
        "oai:doaj.org:article/abc123",
        "oai:openaire.eu:publication:12345",
    ],
)
def test_valid_oai_formats(valid_oai: str) -> None:
    sut = Oai(valid_oai)
    assert str(sut) == valid_oai


@pytest.mark.parametrize(
    "invalid_oai",
    [
        "",
        " ",
        "something:arXiv.org:hep-th/9901001",
        "oai:arXiv.org:hep-th/99010 01",
        "oai:999:abc123",
        "oai:wibble:abc123",
        "oai:",
        "oai:foo.org:",
        "oai::local-id",
        "notanoai",
        "oai",
        "oai:foo",
    ],
)
def test_invalid_oai_formats(invalid_oai: str) -> None:
    with pytest.raises(ValueError):
        Oai(invalid_oai)


def test_oai_url_returns_none() -> None:
    """OAI identifiers don't have a standard HTTP resolution."""
    sut = Oai("oai:arXiv.org:hep-th/9901001")

    assert sut.url() is None


def test_oai_is_case_sensitive() -> None:
    """OAI identifiers are case-sensitive."""
    oai1 = Oai("oai:foo.org:some-local-id-53")
    oai2 = Oai("oai:FOO.ORG:some-local-id-53")

    assert oai1 != oai2
    assert str(oai1) != str(oai2)
