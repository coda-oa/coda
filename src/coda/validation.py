import functools
from typing import ParamSpec, TypeVar
from collections.abc import Callable

from django.core.exceptions import ValidationError

P = ParamSpec("P")
T = TypeVar("T")


def as_validator(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator that converts errors raised by the given function into a ValidationError.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except Exception as err:
            raise ValidationError(str(err)) from err

    return wrapper
