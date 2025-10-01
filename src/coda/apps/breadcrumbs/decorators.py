from functools import wraps
from typing import Any, Callable
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
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """
    Decorator to add breadcrumb navigation to Django views.
    
    Args:
        title: The display title for this page in the breadcrumb
        parent_url_name: The URL name of the parent page (e.g., 'invoices:list')
        preserve_filters: Whether to preserve URL parameters when navigating back
        exclude_params: List of parameter names to exclude when preserving filters
    
    Example:
        @breadcrumb("Invoice Details", parent_url_name="invoices:list")
        def invoice_detail(request, pk):
            # your view code
            pass
    """
    if exclude_params is None:
        exclude_params = ['page']  # Typically we don't want to preserve pagination
    
    def decorator(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            # Store breadcrumb info on the request for later use
            if not hasattr(request, '_breadcrumb_data'):
                setattr(request, '_breadcrumb_data', {})
            
            # Resolve title - it can be a string or a callable
            resolved_title = title
            if callable(title):
                resolved_title = title(request, *args, **kwargs)

            resolved_parent  = parent_url_name
            if callable(parent_url_name):
                resolved_parent = parent_url_name(request, *args, **kwargs)
            
            # Store the HTTP referer to preserve filters from the previous page
            referer_url = request.META.get('HTTP_REFERER', '')
            
            breadcrumb_data = getattr(request, '_breadcrumb_data', {})
            breadcrumb_data.update({
                'title': resolved_title,
                'parent_url_name': resolved_parent,
                'preserve_filters': preserve_filters,
                'exclude_params': exclude_params,
                'referer_url': referer_url,
                'view_args': args,
                'view_kwargs': kwargs,
            })
            
            return view_func(request, *args, **kwargs)
        
        # Store metadata on the function for introspection using setattr to avoid mypy issues
        setattr(wrapper, 'breadcrumb_title', title)
        setattr(wrapper, 'breadcrumb_parent', parent_url_name)
        setattr(wrapper, 'breadcrumb_preserve_filters', preserve_filters)
        setattr(wrapper, 'breadcrumb_exclude_params', exclude_params)
        
        return wrapper
    
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
    default_title: str = "Details"
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



