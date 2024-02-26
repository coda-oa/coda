import functools
from typing import TypeVar
from collections.abc import Callable

from django.core.exceptions import ValidationError

T = TypeVar("T")


def as_validator(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that converts errors raised by the given function into a ValidationError.
    """

    @functools.wraps(func)
    def wrapper(value: T) -> T:
        try:
            return func(value)
        except Exception as err:
            raise ValidationError(str(err)) from err

    return wrapper
