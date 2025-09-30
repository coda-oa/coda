from typing import Any, Dict
from django.http import HttpRequest
from django.urls import resolve, reverse, NoReverseMatch


def resolve_breadcrumb_metadata(url_name: str, request: HttpRequest, **url_kwargs: Any) -> Dict[str, Any]:
    """
    Resolve breadcrumb metadata from an actual view without executing it.
    
    Args:
        url_name: The URL name to resolve
        request: The current request (for context)
        **url_kwargs: URL kwargs like pk for detail views
    
    Returns:
        Dictionary with breadcrumb metadata (title, parent_url_name, etc.)
    """
    try:
        # Build the URL - try with provided kwargs first, then without if that fails
        url = None
        try:
            url = reverse(url_name, kwargs=url_kwargs)
        except NoReverseMatch:
            # If kwargs don't work for this URL, try without them
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                return {}
        
        if not url:
            return {}
        
        # Resolve the view function/class
        resolver_match = resolve(url)
        view_func = resolver_match.func
        
        # Check if the view has breadcrumb metadata
        breadcrumb_metadata = {}
        
        # For function-based views with decorators
        if hasattr(view_func, 'breadcrumb_title'):
            title = getattr(view_func, 'breadcrumb_title')
            
            # If it's a callable (dynamic title), we need to call it
            if callable(title):
                try:
                    # Call the dynamic title function with the same args it would receive
                    title = title(request, *resolver_match.args, **resolver_match.kwargs)
                except Exception:
                    # If the dynamic title function fails, use a fallback
                    title = "Details"
            
            breadcrumb_metadata = {
                'title': title,
                'parent_url_name': getattr(view_func, 'breadcrumb_parent', None),
                'preserve_filters': getattr(view_func, 'breadcrumb_preserve_filters', True),
                'exclude_params': getattr(view_func, 'breadcrumb_exclude_params', ['page']),
            }
        
        # For class-based views with breadcrumb mixins
        elif hasattr(view_func, 'view_class'):
            view_class = view_func.view_class
            if hasattr(view_class, 'breadcrumb_title'):
                title = view_class.breadcrumb_title
                
                # Handle callable titles for class-based views
                if callable(title):
                    try:
                        # This is trickier for class-based views, might need different approach
                        title = "Details"  # Fallback for now
                    except Exception:
                        title = "Details"
                
                breadcrumb_metadata = {
                    'title': title,
                    'parent_url_name': getattr(view_class, 'breadcrumb_parent_url_name', None),
                    'preserve_filters': getattr(view_class, 'breadcrumb_preserve_filters', True),
                    'exclude_params': getattr(view_class, 'breadcrumb_exclude_params', ['page']),
                }
        
        return breadcrumb_metadata
        
    except (NoReverseMatch, Exception):
        # If resolution fails, return empty metadata
        return {}


def extract_url_kwargs_from_url(url: str, url_name: str) -> Dict[str, Any]:
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
        if resolver_match.url_name == url_name.split(':')[-1]:  # Handle namespaced URLs
            return resolver_match.kwargs
    except Exception:
        pass
    return {}