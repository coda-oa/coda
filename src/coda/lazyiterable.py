from collections.abc import Generator, Iterable
from typing import TypeVar

T = TypeVar("T")


class LazyCachedIterable(Iterable[T]):
    __slots__ = ("_generator", "_resolved_items")

    def __init__(self, generator: Generator[T, None, None]) -> None:
        self._generator = generator
        self._resolved_items: list[T] = []

    def __iter__(self) -> Generator[T, None, None]:
        for item in self._resolved_items:
            yield item

        for item in self._generator:
            self._resolved_items.append(item)
            yield item
