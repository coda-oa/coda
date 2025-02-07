import pytest
from coda.publication.links import Isbn


VALID_ISBN_10 = "1234567890"


@pytest.mark.parametrize(
    "isbn",
    [
        "123456789",
        "12345678901234",
        "123-456-789",
        "123-456-789-012-34",
    ],
    ids=[
        "9 characters",
        "14 characters",
        "9 characters with dashes",
        "14 characters with dashes",
    ],
)
def test__isbn_is_either_10_or_13_characters(isbn: str) -> None:
    with pytest.raises(ValueError):
        Isbn(isbn)
