from typing import Any, Callable, Union

from django.http import HttpRequest, HttpResponseBase
from django.views.generic.base import View

# Type for title - can be string or callable
TitleType = Union[str, Callable[[HttpRequest, Any, Any], str]]


class BreadcrumbMixin(View):
    """
    Mixin for class-based views to add breadcrumb navigation.
    
    Usage:
        class MyView(BreadcrumbMixin, ListView):
            breadcrumb_title = "My Page"
            breadcrumb_parent_url_name = "parent:view"
            breadcrumb_preserve_filters = True
    """
    breadcrumb_title: TitleType = ""
    breadcrumb_parent_url_name: str = ""
    breadcrumb_preserve_filters: bool = True
    breadcrumb_exclude_params: list[str] = ['page']

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # Add breadcrumb data to the request
        if not hasattr(request, '_breadcrumb_data'):
            setattr(request, '_breadcrumb_data', {})
        
        # Resolve title - it can be a string or a callable
        resolved_title = self.breadcrumb_title
        if callable(self.breadcrumb_title):
            resolved_title = self.breadcrumb_title(request, *args, **kwargs)
        
        # Store the HTTP referer to preserve filters from the previous page
        referer_url = request.META.get('HTTP_REFERER', '')
        
        breadcrumb_data = getattr(request, '_breadcrumb_data', {})
        breadcrumb_data.update({
            'title': resolved_title,
            'parent_url_name': self.breadcrumb_parent_url_name,
            'preserve_filters': self.breadcrumb_preserve_filters,
            'exclude_params': self.breadcrumb_exclude_params,
            'referer_url': referer_url,
            'view_args': args,
            'view_kwargs': kwargs,
        })
        
        return super().dispatch(request, *args, **kwargs)