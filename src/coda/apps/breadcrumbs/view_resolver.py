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
        url = _build_url_with_fallback(url_name, url_kwargs, request)
        if not url:
            return {}

        view_func = _resolve_view_function(url, request)
        return _extract_breadcrumb_metadata(view_func, request, url)

    except Exception:
        return {}


def _build_url_with_fallback(
    url_name: str, url_kwargs: dict[str, Any], request: HttpRequest
) -> str | None:
    """Build URL with kwargs, falling back to no kwargs if needed. Handles SCRIPT_NAME properly."""
    try:
        url = reverse(url_name, kwargs=url_kwargs)
        return _normalize_url_for_script_name(url, request)
    except NoReverseMatch:
        try:
            url = reverse(url_name)
            return _normalize_url_for_script_name(url, request)
        except NoReverseMatch:
            return None


def _resolve_view_function(url: str, request: HttpRequest) -> Any:
    """Resolve URL to view function. Handles SCRIPT_NAME properly."""
    # Strip SCRIPT_NAME prefix if present for resolution
    path_for_resolution = _strip_script_name_from_url(url, request)
    resolver_match = resolve(path_for_resolution)
    return resolver_match.func


def _normalize_url_for_script_name(url: str, request: HttpRequest) -> str:
    """
    Ensure URL is properly formatted for the current SCRIPT_NAME context.
    """
    script_name = getattr(request, "META", {}).get("SCRIPT_NAME", "")
    if script_name and not url.startswith(script_name):
        # Add SCRIPT_NAME prefix if not already present
        return str(script_name).rstrip("/") + url
    return url


def _strip_script_name_from_url(url: str, request: HttpRequest) -> str:
    """
    Strip SCRIPT_NAME prefix from URL for proper resolution.
    """
    script_name = getattr(request, "META", {}).get("SCRIPT_NAME", "")
    if script_name and url.startswith(str(script_name)):
        # Remove SCRIPT_NAME prefix for resolution
        return url[len(str(script_name).rstrip("/")) :]
    return url


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
        # Strip SCRIPT_NAME prefix if present for resolution
        path_for_resolution = _strip_script_name_from_url(url, request)
        resolver_match = resolve(path_for_resolution)
        result = title(request, *resolver_match.args, **resolver_match.kwargs)
        return str(result)  # Ensure we return a string
    except Exception:
        return "Details"


def extract_url_kwargs_from_url(
    url: str, url_name: str, request: HttpRequest | None = None
) -> dict[str, Any]:
    """
    Extract URL kwargs (like pk) from a URL path.

    Args:
        url: The URL path
        url_name: The URL name to resolve against
        request: The current request (for SCRIPT_NAME handling)

    Returns:
        Dictionary of URL kwargs
    """
    try:
        # Strip SCRIPT_NAME prefix if present for resolution
        if request:
            url = _strip_script_name_from_url(url, request)

        resolver_match = resolve(url)
        if resolver_match.url_name == url_name.split(":")[-1]:  # Handle namespaced URLs
            return resolver_match.kwargs
    except Exception:
        pass
    return {}
