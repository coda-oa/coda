from typing import Any, Dict

from django.http import HttpRequest
from django.urls import reverse

from .decorators import build_breadcrumb_url, get_preserved_query_params, extract_filters_from_referer
from .view_resolver import resolve_breadcrumb_metadata


def _build_breadcrumb_hierarchy(url_name: str, request: HttpRequest, query_params: str = "", **original_kwargs: Any) -> list[dict[str, Any]]:
    """
    Recursively build the complete breadcrumb hierarchy from a given URL name.
    Uses actual view metadata instead of static mapping.
    
    Args:
        url_name: The starting URL name (e.g., 'invoices:list')
        request: The current request (needed for dynamic title resolution)
        query_params: Query parameters to preserve
        **original_kwargs: URL kwargs from the original view (like pk)
    
    Returns:
        List of breadcrumb dictionaries in hierarchical order
    """
    breadcrumbs: list[dict[str, Any]] = []
    
    # Recursively build the hierarchy by following parent_url_name from views
    current_url_name: str | None = url_name
    current_kwargs = original_kwargs.copy()
    visited = set()  # Prevent infinite loops
    
    while current_url_name and current_url_name not in visited:
        visited.add(current_url_name)
        
        try:
            # Clear kwargs for views that don't need them (BEFORE building URL)
            url_kwargs = current_kwargs.copy()
            if current_url_name.endswith(':list') or current_url_name.endswith('_home'):
                # List views and home views don't need pk parameters
                url_kwargs = {}
            
            # Get breadcrumb metadata from the actual view
            metadata = resolve_breadcrumb_metadata(current_url_name, request, **url_kwargs)
            
            if not metadata:
                # If we can't resolve metadata, fall back to static mapping
                title = _get_title_from_url_name(current_url_name)
                parent_url_name = _get_static_parent_mapping().get(current_url_name)
            else:
                title = metadata.get('title', _get_title_from_url_name(current_url_name))
                parent_url_name = metadata.get('parent_url_name')
            
            # Build URL for current level using cleaned kwargs
            if current_url_name == url_name:
                # For the original URL, use the provided query params (with filters)
                breadcrumb_url = build_breadcrumb_url(current_url_name, query_params, **url_kwargs)
            else:
                # For parent URLs, don't preserve filters
                breadcrumb_url = build_breadcrumb_url(current_url_name, "", **url_kwargs)
            
            # Insert at beginning to maintain correct order
            breadcrumbs.insert(0, {
                'title': title,
                'url': breadcrumb_url,
                'is_current': False
            })
            
            # Move to parent - pass kwargs for the next iteration
            current_url_name = parent_url_name
            # Keep current_kwargs for next iteration (they'll be cleaned as needed)
            
        except Exception:
            # If URL building fails, stop the hierarchy building
            break
    
    return breadcrumbs


def _get_static_parent_mapping() -> Dict[str, str | None]:
    """
    Fallback static hierarchy mapping for views without breadcrumb metadata.
    """
    return {
        'invoices:list': 'invoices:finances_home',
        'invoices:detail': 'invoices:list',
        'invoices:create': 'invoices:list',
        'invoices:update': 'invoices:detail',
        'invoices:creditor_list': 'invoices:finances_home',
        'invoices:creditor_detail': 'invoices:creditor_list',
        'invoices:creditor_create': 'invoices:creditor_list',
        'invoices:finances_home': None,  # Top level under Home
        'contracts:list': None,
        'contracts:detail': 'contracts:list',
        'fundingrequests:list': None,
        'fundingrequests:detail': 'fundingrequests:list',
        'publications:list': None,
        'publications:detail': 'publications:list',
        'authors:list': None,
        'authors:detail': 'authors:list',
        'institutions:list': None,
        'institutions:detail': 'institutions:list',
    }


def breadcrumb_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Context processor that automatically generates breadcrumb navigation data.
    
    This processor looks for breadcrumb metadata attached to the current view
    and builds a complete breadcrumb trail with preserved URL parameters.
    
    Returns a context dictionary with:
    - breadcrumbs: List of breadcrumb items with 'title' and 'url' keys
    - current_page_title: Title of the current page
    """
    breadcrumbs: list[dict[str, Any]] = []
    current_page_title = ""
    
    # Check if the current view has breadcrumb data
    if not hasattr(request, '_breadcrumb_data'):
        return {'breadcrumbs': breadcrumbs, 'current_page_title': current_page_title}
    
    breadcrumb_data = getattr(request, '_breadcrumb_data', {})
    current_page_title = breadcrumb_data.get('title', '')
    
    # If there's a parent URL, build the complete breadcrumb hierarchy
    parent_url_name = breadcrumb_data.get('parent_url_name')
    if parent_url_name:
        preserve_filters = breadcrumb_data.get('preserve_filters', True)
        exclude_params = breadcrumb_data.get('exclude_params', ['page'])
        
        # Get preserved query parameters if needed
        query_params = ""
        if preserve_filters:
            # Try to get filters from the referer URL first (when user came from a filtered list)
            referer_url = breadcrumb_data.get('referer_url', '')
            if referer_url:
                query_params = extract_filters_from_referer(referer_url, exclude_params)
            
            # Fallback to current request parameters if no referer filters found
            if not query_params:
                query_params = get_preserved_query_params(request, exclude_params)
        
        # Extract URL kwargs from the current request for proper URL building
        current_kwargs = {}
        try:
            from django.urls import resolve
            resolver_match = resolve(request.path)
            current_kwargs = resolver_match.kwargs
        except Exception:
            pass
        
        # Build the complete hierarchical breadcrumb chain
        breadcrumbs = _build_breadcrumb_hierarchy(parent_url_name, request, query_params, **current_kwargs)
    
    # Add home breadcrumb if not already at home
    if breadcrumbs or current_page_title:
        try:
            home_url = reverse('home')
            if request.path != home_url:
                breadcrumbs.insert(0, {
                    'title': 'Home',
                    'url': home_url,
                    'is_current': False
                })
        except Exception:
            pass
    
    return {
        'breadcrumbs': breadcrumbs,
        'current_page_title': current_page_title
    }


def _get_title_from_url_name(url_name: str) -> str:
    """
    Convert URL name to a human-readable title.
    
    You can customize this mapping based on your URL patterns.
    """
    title_mapping = {
        'home': 'Home',
        'invoices:finances_home': 'Finances',
        'invoices:list': 'Invoices',
        'invoices:detail': 'Invoice Details',
        'invoices:create': 'Create Invoice',
        'invoices:creditor_list': 'Creditors',
        'invoices:creditor_detail': 'Creditor Details',
        'contracts:list': 'Contracts',
        'contracts:detail': 'Contract Details',
        'fundingrequests:list': 'Funding Requests',
        'fundingrequests:detail': 'Funding Request Details',
        'publications:list': 'Publications',
        'publications:detail': 'Publication Details',
        'authors:list': 'Authors',
        'authors:detail': 'Author Details',
        'institutions:list': 'Institutions',
        'institutions:detail': 'Institution Details',
    }
    
    return title_mapping.get(url_name, url_name.replace('_', ' ').replace(':', ' - ').title())