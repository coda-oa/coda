from typing import Any

from django import template

register = template.Library()


@register.filter(name="abs")
def absolute(value: Any) -> Any:
    """Absolute value of a number; passes through non-numbers unchanged."""
    try:
        return abs(value)
    except TypeError:
        return value
