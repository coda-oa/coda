import pytest
from coda import issn


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
