from typing import Any
from django import template

register = template.Library()


@register.filter(name="getitem")
def get_item(dictionary: dict[str, Any], key: str) -> Any:
    return dictionary.get(key)
