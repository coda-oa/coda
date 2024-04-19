from typing import Self


class NonEmptyStr(str):
    def __new__(cls, value: str) -> Self:
        if value is None or not value.strip():
            raise ValueError("Value is required")

        return super().__new__(cls, value)
