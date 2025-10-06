from functools import wraps
from typing import Any
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.http import urlencode as django_urlencode

# Type for title - can be string or callable that takes request, *args, **kwargs
TitleType = str | Callable[[HttpRequest, Any, Any], str]


def breadcrumb(
    title: TitleType,
    parent_url_name: str | Callable[[HttpRequest, Any, Any], str] | None = None,
    preserve_filters: bool = True,
    exclude_params: list[str] | None = None,
) -> Callable[[Any], Any]:
    """
    Decorator to add breadcrumb navigation to Django views.
    Works with both function-based and class-based views.

    Args:
        title: The display title for this page in the breadcrumb
        parent_url_name: The URL name of the parent page (e.g., 'invoices:list')
        preserve_filters: Whether to preserve URL parameters when navigating back
        exclude_params: List of parameter names to exclude when preserving filters

    Usage example:
        @breadcrumb("Invoice Details", parent_url_name="invoices:list")
        def invoice_detail(request, pk):
            # your view code
            pass

    """
    if exclude_params is None:
        exclude_params = ["page"]  # Typically we don't want to preserve pagination

    def _setup_breadcrumb_data(request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Extract and set up breadcrumb data on the request object."""
        if not hasattr(request, "_breadcrumb_data"):
            setattr(request, "_breadcrumb_data", {})

        # Resolve title - it can be a string or a callable
        resolved_title = title
        if callable(title):
            resolved_title = title(request, *args, **kwargs)

        resolved_parent = parent_url_name
        if callable(parent_url_name):
            resolved_parent = parent_url_name(request, *args, **kwargs)

        # Store the HTTP referer to preserve filters from the previous page
        referer_url = getattr(request, "META", {}).get("HTTP_REFERER", "")

        breadcrumb_data = getattr(request, "_breadcrumb_data", {})
        breadcrumb_data.update(
            {
                "title": resolved_title,
                "parent_url_name": resolved_parent,
                "preserve_filters": preserve_filters,
                "exclude_params": exclude_params,
                "referer_url": referer_url,
                "view_args": args,
                "view_kwargs": kwargs,
            }
        )

    def _add_breadcrumb_metadata(func: Callable[..., Any]) -> None:
        """Add breadcrumb metadata to a function for introspection."""
        setattr(func, "breadcrumb_title", title)
        setattr(func, "breadcrumb_parent", parent_url_name)
        setattr(func, "breadcrumb_preserve_filters", preserve_filters)
        setattr(func, "breadcrumb_exclude_params", exclude_params)

    def _create_view_wrapper(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        """Create the actual wrapper function for a view function."""

        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            _setup_breadcrumb_data(request, *args, **kwargs)
            return view_func(request, *args, **kwargs)

        _add_breadcrumb_metadata(wrapper)
        return wrapper

    def decorator(view_or_class: Any) -> Any:
        """
        Main decorator function that handles both functions and classes.
        """
        # Check if we're decorating a class (class-based view)
        if isinstance(view_or_class, type):
            # For class-based views, we need to wrap the dispatch method
            # We use a custom wrapper that properly handles the self parameter

            original_dispatch = getattr(view_or_class, "dispatch", None)
            if not original_dispatch:
                raise ValueError(
                    f"Cannot apply breadcrumb decorator to class {view_or_class.__name__}: "
                    "no dispatch method found. Make sure it's a proper Django view class."
                )

            def new_dispatch(self: Any, request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
                _setup_breadcrumb_data(request, *args, **kwargs)
                return original_dispatch(self, request, *args, **kwargs)

            _add_breadcrumb_metadata(new_dispatch)

            # Replace the dispatch method
            setattr(view_or_class, "dispatch", new_dispatch)

            return view_or_class
        else:
            # For function-based views, apply the wrapper directly
            return _create_view_wrapper(view_or_class)

    return decorator


def get_preserved_query_params(request: HttpRequest, exclude_params: list[str]) -> str:
    """
    Get URL query parameters while excluding specified parameters.

    Args:
        request: Django HTTP request object
        exclude_params: List of parameter names to exclude

    Returns:
        URL-encoded query string
    """
    params: dict[str, str] = {}
    for key, value in request.GET.items():
        if key not in exclude_params:
            # Convert to string to satisfy mypy
            params[key] = str(value)

    return django_urlencode(params) if params else ""


def build_breadcrumb_url(url_name: str, query_params: str = "", **url_kwargs: Any) -> str:
    """
    Build a URL for breadcrumb navigation with preserved query parameters.

    Args:
        url_name: Django URL pattern name
        query_params: URL-encoded query string
        **url_kwargs: Additional URL parameters (like pk for detail views)

    Returns:
        Complete URL with query parameters
    """
    try:
        base_url = reverse(url_name, kwargs=url_kwargs)
        if query_params:
            return f"{base_url}?{query_params}"
        return base_url
    except Exception:
        # Fallback if URL resolution fails
        return "/"


def extract_filters_from_referer(referer_url: str, exclude_params: list[str]) -> str:
    """
    Extract query parameters from a referer URL, excluding specified parameters.

    Args:
        referer_url: The HTTP referer URL
        exclude_params: List of parameter names to exclude

    Returns:
        URL-encoded query string with preserved filters
    """
    if not referer_url:
        return ""

    try:
        parsed_url = urlparse(referer_url)
        query_params = parse_qs(parsed_url.query)

        # Filter out excluded parameters and flatten values
        filtered_params: dict[str, str] = {}
        for key, values in query_params.items():
            if key not in exclude_params and values:
                # Take the first value if multiple values exist
                filtered_params[key] = str(values[0])

        return django_urlencode(filtered_params) if filtered_params else ""
    except Exception:
        return ""


def generate_dynamic_title(
    model_name: str,
    fetch_fn: Callable[[str], Any],
    label_attr: str = "name",
    fallback_attr: str = "id",
    default_title: str = "Details",
) -> Callable[[HttpRequest, Any, Any], str]:
    def _title(request: HttpRequest, *args: Any, **kwargs: Any) -> str:
        try:
            pk = kwargs.get("pk") or (args[0] if args else None)
            if not pk:
                return default_title
            obj = fetch_fn(pk)
            label = getattr(obj, label_attr, None)
            if label:
                return f"{model_name} {label}"
            fallback = getattr(obj, fallback_attr, None)
            if fallback:
                return f"{model_name} #{fallback}"
        except Exception:
            pass
        return default_title

    return _title
