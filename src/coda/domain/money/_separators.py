import enum


class DecimalSeparator(enum.Enum):
    """Decimal separator used when rendering money values (Excel locale)."""

    English = "."
    German = ","

    @property
    def display(self) -> str:
        match self:
            case DecimalSeparator.English:
                return ". (English/ISO)"
            case DecimalSeparator.German:
                return ", (e.g. German)"
        return f"{self.value} ({self.name})"
