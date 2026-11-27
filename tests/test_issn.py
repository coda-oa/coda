import pytest

from coda.domain import issn


@pytest.mark.parametrize(
    "partial_issn, expected",
    [
        ("0317-847", "1"),
        ("0378-595", "5"),
        ("2049-363", "0"),
        ("2434-561", "X"),
        ("0317-8471", "1"),
        ("0378-5955", "5"),
        ("2049-3630", "0"),
        ("2434-561X", "X"),
    ],
)
def test__issn_checksum(partial_issn: str, expected: str) -> None:
    assert issn.checksum(partial_issn) == expected


@pytest.mark.parametrize(
    "value",
    [
        "123456789",  # nine digits, the old validator accepted this shape
        "2434-561XX",
        "2434-561",
    ],
)
def test__issn__rejects_non_canonical_length(value: str) -> None:
    with pytest.raises(ValueError):
        issn.Issn(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2434-561X", "2434-561X"),
        ("2434561X", "2434-561X"),
        ("2434-561x", "2434-561X"),
        ("123-45679", "1234-5679"),
        ("00280836", "0028-0836"),
        (" 0028-0836 ", "0028-0836"),
    ],
)
def test__issn__is_normalised_to_canonical_form(value: str, expected: str) -> None:
    assert issn.Issn(value) == expected


def test__issn__must_have_correct_checksum() -> None:
    with pytest.raises(ValueError):
        invalid_checksum = issn.Issn("2434-561A")  # noqa: F841

    with pytest.raises(ValueError):
        issn.Issn("24345618")
