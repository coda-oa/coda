import pytest

from coda.string import NonEmptyStr


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        None,
    ],
)
def test__non_empty_str__requires_value(value: str) -> None:
    with pytest.raises(ValueError):
        NonEmptyStr(value)
