from typing import Any
from django.http import HttpRequest
from django.urls import resolve, reverse, NoReverseMatch


def resolve_breadcrumb_metadata(
    url_name: str, request: HttpRequest, **url_kwargs: Any
) -> dict[str, Any]:
    """
    Resolve breadcrumb metadata from a view function with breadcrumb decorators.

    Args:
        url_name: The URL name to resolve
        request: The current request (for context)
        **url_kwargs: URL kwargs like pk for detail views

    Returns:
        Dictionary with breadcrumb metadata (title, parent_url_name, etc.)
    """
    try:
        url = _build_url_with_fallback(url_name, url_kwargs)
        if not url:
            return {}

        view_func = _resolve_view_function(url)
        return _extract_breadcrumb_metadata(view_func, request, url)

    except Exception:
        return {}


def _build_url_with_fallback(url_name: str, url_kwargs: dict[str, Any]) -> str | None:
    """Build URL with kwargs, falling back to no kwargs if needed."""
    try:
        return reverse(url_name, kwargs=url_kwargs)
    except NoReverseMatch:
        try:
            return reverse(url_name)
        except NoReverseMatch:
            return None


def _resolve_view_function(url: str) -> Any:
    """Resolve URL to view function."""
    resolver_match = resolve(url)
    return resolver_match.func


def _extract_breadcrumb_metadata(view_func: Any, request: HttpRequest, url: str) -> dict[str, Any]:
    """Extract breadcrumb metadata from a decorated view function."""
    if not hasattr(view_func, "breadcrumb_title"):
        return {}

    title = getattr(view_func, "breadcrumb_title")
    resolved_title = _resolve_dynamic_title(title, request, url)

    return {
        "title": resolved_title,
        "parent_url_name": getattr(view_func, "breadcrumb_parent", None),
        "preserve_filters": getattr(view_func, "breadcrumb_preserve_filters", True),
        "exclude_params": getattr(view_func, "breadcrumb_exclude_params", ["page"]),
    }


def _resolve_dynamic_title(title: Any, request: HttpRequest, url: str) -> str:
    """Resolve title, calling it if it's a callable."""
    if not callable(title):
        return str(title)  # Ensure we return a string

    try:
        resolver_match = resolve(url)
        result = title(request, *resolver_match.args, **resolver_match.kwargs)
        return str(result)  # Ensure we return a string
    except Exception:
        return "Details"


def extract_url_kwargs_from_url(url: str, url_name: str) -> dict[str, Any]:
    """
    Extract URL kwargs (like pk) from a URL path.

    Args:
        url: The URL path
        url_name: The URL name to resolve against

    Returns:
        Dictionary of URL kwargs
    """
    try:
        resolver_match = resolve(url)
        if resolver_match.url_name == url_name.split(":")[-1]:  # Handle namespaced URLs
            return resolver_match.kwargs
    except Exception:
        pass
    return {}
