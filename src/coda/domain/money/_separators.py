import enum
from decimal import Decimal


class DecimalSeparator(enum.Enum):
    """Decimal separator used when rendering money values (Excel locale)."""

    English = "."
    German = ","

    def render(self, value: Decimal | float | str | None) -> str | None:
        """Render a value with this locale's decimal separator.

        ``None`` passes through (blank comparison cells); ``Decimal`` and
        ``float`` render via ``str()`` — for :attr:`English` that is the
        identity, preserving ``str(Decimal)``'s scale.
        """
        if value is None:
            return None
        text = str(value)
        if self is DecimalSeparator.German:
            return text.replace(".", ",")
        return text

    @property
    def display(self) -> str:
        match self:
            case DecimalSeparator.English:
                return ". (English/ISO)"
            case DecimalSeparator.German:
                return ", (e.g. German)"
        return f"{self.value} ({self.name})"
