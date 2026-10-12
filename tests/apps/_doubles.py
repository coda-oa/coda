"""Test doubles for version module tests."""


class RecordingCache:
    """Cache double that also records the timeout each key was stored with."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(values or {})
        self.timeouts: dict[str, int] = {}

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def set(self, key: str, value: str, timeout: int | None = None) -> None:
        self.values[key] = value
        self.timeouts[key] = int(timeout) if timeout is not None else 0
