from django import template
from django.http import QueryDict

register = template.Library()


@register.filter
def getlist(dictionary: QueryDict, key: str) -> list[str]:
    return dictionary.getlist(key)
