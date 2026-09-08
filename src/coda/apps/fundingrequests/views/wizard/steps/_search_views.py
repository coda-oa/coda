"""
Factory for HTMX entity search views.
"""

from collections.abc import Callable, Iterable
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST


def make_search_view(
    *,
    param_name: str,
    search_fn: Callable[[str], Iterable[Any]],
    results_key: str,
    results_template: str,
) -> Callable[[HttpRequest], HttpResponse]:
    """Return an HTMX search view for a given entity type.

    Args:
        param_name: POST parameter name carrying the search term.
        search_fn: Service-layer callable that accepts the search term and
                   returns a sequence of matching model instances.
        results_key: Template context key under which results are passed.
        results_template: Path to the search-results partial template.
    """

    @login_required
    @require_POST
    def _view(request: HttpRequest) -> HttpResponse:
        search_term = request.POST.get(param_name, "").strip()
        results = search_fn(search_term)
        return render(
            request,
            results_template,
            {
                results_key: results,
                "search_term": search_term,
            },
        )

    return _view

@require_POST
def clear_validation_error(request: HttpRequest) -> HttpResponse:
    """Empty acknowledgement; htmx swaps it into an inline error list to clear it."""
    return HttpResponse()
