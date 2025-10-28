from typing import Any


DEFAULT_FIELD_SEPARATOR = "-"
SEQUENCE_COUNTER_PREFIX = "#"
_SEQUENCE_LENGTH = f"{SEQUENCE_COUNTER_PREFIX}{DEFAULT_FIELD_SEPARATOR}{{field_name}}"


class KeyMatcher:
    """Utility class for handling key matching and prefix operations in form data."""

    def __init__(self, separator: str = DEFAULT_FIELD_SEPARATOR):
        self.separator = separator

    def strip_prefix(self, data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """Remove prefix from all keys in data and return new dict."""
        if not prefix:
            return data.copy()

        strip = prefix + self.separator
        return {k.removeprefix(strip): v for k, v in data.items()}

    def get_keys_with_prefix(self, data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """Get all key-value pairs where key starts with prefix."""
        prefix_with_separator = prefix + self.separator
        return {k: v for k, v in data.items() if k.startswith(prefix_with_separator)}

    def build_sequence_key(self, field_name: str, index: int) -> str:
        """Build key for sequence item: field_name-index."""
        return f"{field_name}{self.separator}{index}"

    def build_counter_key(self, field_name: str) -> str:
        """Build counter key: #-field_name."""
        return _SEQUENCE_LENGTH.format(field_name=field_name)

    def matches_field_pattern(self, key: str, field_name: str) -> bool:
        """Check if key matches field pattern (exact match or starts with field_name-)."""
        return (
            key == field_name
            or key.startswith(field_name + self.separator)
            or key == self.build_counter_key(field_name)
        )
