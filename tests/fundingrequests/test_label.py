import pytest
from django.core.exceptions import ValidationError

from coda.apps.fundingrequests.models import Label


@pytest.mark.parametrize(
    "color",
    ["red", "#12345", "#GGGGGG", "#123", "#1234567"],
)
def test__invalid_hex_color__raises_error(color: str) -> None:
    with pytest.raises(ValidationError):
        Label(name="Test", hexcolor=color).full_clean()


def test__valid_hex_color__no_error() -> None:
    Label(name="Test", hexcolor="#123456").full_clean()
    Label(name="Test", hexcolor="#ABCDEF").full_clean()
