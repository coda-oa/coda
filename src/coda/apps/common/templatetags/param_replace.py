from typing import Any
from django.http import HttpRequest
from django.template import Library


register = Library()


@register.simple_tag(takes_context=True)
def param_replace(context: dict[str, Any], **kwargs: Any) -> str:
    """
    Adds keyword arguments to the current page's GET parameters.
    Based on https://www.caktusgroup.com/blog/2018/10/18/filtering-and-pagination-django/
    """
    request: HttpRequest = context["request"]
    query = request.GET.copy()
    for key, value in kwargs.items():
        query[key] = value

    empty_params = [key for key, value in query.items() if not value]
    for key in empty_params:
        del query[key]

    return query.urlencode()
