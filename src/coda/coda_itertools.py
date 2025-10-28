from collections.abc import Generator, Iterable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class LazyCachedIterable(Iterable[T]):
    __slots__ = ("_generator", "_resolved_items")

    def __init__(self, generator: Generator[T, None, None]) -> None:
        self._generator = generator
        self._resolved_items: list[T] = []

    def __bool__(self) -> bool:
        if self._resolved_items:
            return True

        try:
            next(iter(self))
        except StopIteration:
            return False

        return True

    def __iter__(self) -> Iterator[T]:
        for item in self._resolved_items:
            yield item

        for item in self._generator:
            self._resolved_items.append(item)
            yield item


TNotNone = TypeVar("TNotNone", bound=object)


class notnone(Iterable[TNotNone], Generic[TNotNone]):
    def __init__(self, iterable: Iterable[TNotNone | None]) -> None:
        self._iterable = iterable

    def __iter__(self) -> Iterator[TNotNone]:
        return iter(item for item in self._iterable if item is not None)
