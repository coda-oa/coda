from __future__ import annotations

from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from types import TracebackType
from typing import Concatenate, TypeIs, final

from coda.coda_itertools import LazyCachedIterable


class DomainError(ValueError):
    """A base class for all domain errors"""


type MapEx[Ex: BaseException, NewEx: BaseException, **P] = Callable[Concatenate[Ex, P], NewEx]


@final
@dataclass(slots=True, frozen=True)
class Result[T, Ex: BaseException]:
    _value: T | None
    _exception: Ex | None

    @classmethod
    def success(cls, value: T) -> Result[T, Ex]:
        return cls(value, None)

    @classmethod
    def failed(cls, exception: Ex) -> Result[T, Ex]:
        return cls(None, exception)

    def _ok(self, value: T | None) -> TypeIs[T]:
        return value is not None

    def ok(self) -> bool:
        return self._ok(self._value)

    def get(self) -> T:
        if not self._ok(self._value):
            raise ValueError("tried to get result of failed result")

        return self._value

    def get_or(self, default: T) -> T:
        if not self._ok(self._value):
            return default

        return self._value

    def get_err(self) -> Ex:
        if self._exception is None:
            raise ValueError("tried to get exception from successful result")

        return self._exception

    def map_err[NewEx: BaseException, **P](
        self, fn: MapEx[Ex, NewEx, P], *args: P.args, **kwargs: P.kwargs
    ) -> Result[T, NewEx]:
        if self._exception is not None:
            return Result.failed(fn(self._exception, *args, **kwargs))

        return Result.success(self.get())


@dataclass(slots=True)
class ResultCollection[T, Ex: BaseException]:
    results: Iterable[Result[T, Ex]]

    def __post_init__(self) -> None:
        if isinstance(self.results, Generator):
            self.results = LazyCachedIterable(self.results)

    def has_errors(self) -> bool:
        return any(not r.ok() for r in self.results)

    def values(self) -> list[T]:
        return [r.get() for r in self.results if r.ok()]

    def errors(self) -> list[Ex]:
        return [r.get_err() for r in self.results if not r.ok()]

    def split(self) -> tuple[list[T], list[Ex]]:
        return self.values(), self.errors()


class CaptureContext[Ex: BaseException]:
    def __init__(self, exception_type: type[Ex]) -> None:
        self._ex_type = exception_type

    def __enter__(self) -> CaptureContext[Ex]:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass

    def __call__[T, **P](
        self, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> Result[T, Ex]:
        try:
            return Result.success(fn(*args, **kwargs))
        except self._ex_type as e:
            return Result.failed(e)


def capture[Ex: BaseException](exception_type: type[Ex]) -> CaptureContext[Ex]:
    return CaptureContext(exception_type)


def results[T, Ex: BaseException](res: Iterable[Result[T, Ex]]) -> ResultCollection[T, Ex]:
    return ResultCollection(res)
