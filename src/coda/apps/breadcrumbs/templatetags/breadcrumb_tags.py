from typing import Any, Dict

from django import template
from django.http import HttpRequest

from ..decorators import build_breadcrumb_url, get_preserved_query_params

register = template.Library()


@register.simple_tag(takes_context=True)
def breadcrumb_url(context: Dict[str, Any], url_name: str, preserve_filters: bool = True, **kwargs: Any) -> str:
    """
    Template tag to build URLs with preserved filters for breadcrumbs.
    
    Usage:
        {% breadcrumb_url 'invoices:list' %}
        {% breadcrumb_url 'invoices:detail' pk=invoice.id preserve_filters=False %}
    """
    request: HttpRequest = context['request']
    
    query_params = ""
    if preserve_filters:
        exclude_params = ['page']  # Don't preserve pagination
        query_params = get_preserved_query_params(request, exclude_params)
    
    return build_breadcrumb_url(url_name, query_params, **kwargs)


@register.inclusion_tag('breadcrumbs/breadcrumb_nav.html', takes_context=True)
def render_breadcrumbs(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Template tag to render the complete breadcrumb navigation.
    
    Usage:
        {% render_breadcrumbs %}
    """
    return {
        'breadcrumbs': context.get('breadcrumbs', []),
        'current_page_title': context.get('current_page_title', ''),
        'request': context['request']
    }


@register.simple_tag(takes_context=True)
def preserve_current_filters(context: Dict[str, Any]) -> str:
    """
    Template tag to get current URL parameters as a query string.
    
    Usage:
        <a href="{% url 'some_view' %}?{% preserve_current_filters %}">Link</a>
    """
    request: HttpRequest = context['request']
    exclude_params = ['page']  # Don't preserve pagination
    return get_preserved_query_params(request, exclude_params)


@register.filter
def add_filters_to_url(url: str, query_string: str) -> str:
    """
    Template filter to add query parameters to a URL.
    
    Usage:
        {{ some_url|add_filters_to_url:preserved_filters }}
    """
    if query_string:
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}{query_string}"
    return url