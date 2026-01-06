import pytest

from coda.domain.publication.links import Arxiv


def test_can_create_arxiv_new_format() -> None:
    sut = Arxiv("1501.00001")

    assert str(sut) == "arXiv:1501.00001"
    assert sut.value() == "arXiv:1501.00001"


def test_can_create_arxiv_old_format() -> None:
    sut = Arxiv("hep-th/9901001")

    assert str(sut) == "arXiv:hep-th/9901001"


def test_arxiv_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Arxiv(" 2101.12345 ")

    assert str(sut) == "arXiv:2101.12345"


@pytest.mark.parametrize(
    "valid_arxiv",
    [
        # Old format (pre-2007): archive/YYMMNNN
        "hep-th/9901001",
        "astro-ph/0702080",
        "math/0309136",
        "cs/0703012",
        # New format (2007-2014): YYMM.NNNN
        "0704.0001",
        "1412.9999",
        # Current format (2015+): YYMM.NNNNN
        "1501.00001",
        "2101.12345",
        "2312.99999",
        # With version suffix
        "1501.00001v1",
        "2101.12345v2",
        "hep-th/9901001v1",
        "0704.0001v3",
        # With arXiv: prefix
        "arXiv:1501.00001",
        "arXiv:0706.0001",
        "arXiv:hep-th/9901001",
        "arXiv:1501.00001v1",
        "arxiv:2101.12345",  # lowercase prefix
    ],
)
def test_valid_arxiv_formats(valid_arxiv: str) -> None:
    sut = Arxiv(valid_arxiv)
    # Should normalize to have arXiv: prefix with proper case
    assert str(sut).startswith("arXiv:")
    assert "/" in str(sut) or "." in str(sut)


@pytest.mark.parametrize(
    "invalid_arxiv",
    [
        "",
        " ",
        "1234",
        "abcd.1234",
        "1501.1",  # too few digits after dot
        "1501.123",  # 3 digits (neither 4 nor 5)
        "1501.123456",  # too many digits
        "not-an-arxiv",
        "1501/00001",  # wrong separator
    ],
)
def test_invalid_arxiv_formats(invalid_arxiv: str) -> None:
    with pytest.raises(ValueError):
        Arxiv(invalid_arxiv)


def test_arxiv_url_returns_arxiv_org_url() -> None:
    sut = Arxiv("1501.00001")

    assert sut.url() == "https://arxiv.org/abs/arXiv:1501.00001"


def test_arxiv_url_with_old_format() -> None:
    sut = Arxiv("hep-th/9901001")

    assert sut.url() == "https://arxiv.org/abs/arXiv:hep-th/9901001"


def test_arxiv_with_version_in_url() -> None:
    sut = Arxiv("1501.00001v2")

    assert sut.url() == "https://arxiv.org/abs/arXiv:1501.00001v2"


def test_arxiv_normalizes_prefix() -> None:
    sut = Arxiv("arXiv:1501.00001")

    assert str(sut) == "arXiv:1501.00001"
    assert sut.url() == "https://arxiv.org/abs/arXiv:1501.00001"


def test_arxiv_normalizes_prefix_case() -> None:
    """Lowercase arxiv: should be normalized to arXiv:"""
    sut = Arxiv("arxiv:hep-th/9901001")

    assert str(sut) == "arXiv:hep-th/9901001"
    assert sut.url() == "https://arxiv.org/abs/arXiv:hep-th/9901001"


def test_arxiv_adds_prefix_when_missing() -> None:
    """Plain identifiers should get arXiv: prefix added."""
    sut = Arxiv("1501.00001")

    assert str(sut) == "arXiv:1501.00001"
