from collections.abc import Callable, Generator, Iterable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class LazyCachedIterable(Iterable[T]):
    """Iterable that fetches from its source only on first use.

    Accepts an already-created generator or a zero-argument factory. Mappers
    must pass a factory when the loop's outer iterable touches the database:
    a generator expression evaluates that iterable — and thus executes an
    unprefetched queryset — at creation time, defeating the point of laziness.
    """

    __slots__ = ("_generator", "_resolved_items", "_source")

    def __init__(self, source: Generator[T, None, None] | Callable[[], Iterable[T]]) -> None:
        if isinstance(source, Generator):
            generator = source
            self._source: Callable[[], Iterable[T]] = lambda: generator
        else:
            self._source = source
        self._generator: Iterator[T] | None = None
        self._resolved_items: list[T] = []

    def _pending(self) -> Iterator[T]:
        if self._generator is None:
            self._generator = iter(self._source())
        return self._generator

    def __bool__(self) -> bool:
        if self._resolved_items:
            return True

        try:
            next(iter(self))
        except StopIteration:
            return False

        return True

    def __iter__(self) -> Iterator[T]:
        yield from self._resolved_items
        for item in self._pending():
            self._resolved_items.append(item)
            yield item


TNotNone = TypeVar("TNotNone", bound=object)


class notnone(Iterable[TNotNone], Generic[TNotNone]):
    def __init__(self, iterable: Iterable[TNotNone | None]) -> None:
        self._iterable = iterable

    def __iter__(self) -> Iterator[TNotNone]:
        return iter(item for item in self._iterable if item is not None)


def map_or_none[T](map_fn: Callable[[str], T], value: str | None) -> T | None:
    """Map ``value``, treating a falsy value or a ``ValueError`` as absent.

    ``ValueError`` is deliberately the catch-all: pydantic's ``ValidationError``
    subclasses it, so a rejected enum member and a rejected field value both
    yield ``None`` instead of aborting the caller.
    """
    if value:
        try:
            return map_fn(value)
        except ValueError:
            return None

    return None
