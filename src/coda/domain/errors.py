from types import TracebackType
from typing import Generic, ParamSpec, TypeVar
from collections.abc import Callable


class DomainError(ValueError):
    """A base class for all domain errors"""


P = ParamSpec("P")
T = TypeVar("T")
Ex = TypeVar("Ex", bound=BaseException)


class CaptureContext(Generic[Ex]):
    def __init__(self, exception_type: type[Ex]) -> None:
        self._ex_type = exception_type
        self.errors: list[Ex] = []

    def __enter__(self) -> "CaptureContext[Ex]":
        return self

    def __exit__(
        self,
        exc_type: type[Exception] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass

    def __call__(self, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T | None:
        try:
            return fn(*args, **kwargs)
        except self._ex_type as e:
            self.errors.append(e)
            return None


def capture(exception_type: type[Ex]) -> CaptureContext[Ex]:
    return CaptureContext(exception_type)
