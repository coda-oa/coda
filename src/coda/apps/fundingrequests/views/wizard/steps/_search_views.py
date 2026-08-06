"""
Factory for HTMX entity search views.

All generated views require POST and login. The ``row_template`` context variable
is injected so callers can override it per deployment context — for example, the
DOI import preview page supplies a stripped-down row template that omits wizard-
specific HTMX interactions (clear_*_error) that don't exist in that context.
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
    default_row_template: str,
) -> Callable[[HttpRequest], HttpResponse]:
    """Return an HTMX search view for a given entity type.

    Args:
        param_name: POST parameter name carrying the search term.
        search_fn: Service-layer callable that accepts the search term and
                   returns a sequence of matching model instances.
        results_key: Template context key under which results are passed.
        results_template: Path to the search-results partial template.
        default_row_template: Path to the row partial used when no override
                              is supplied by the caller.
    """

    @login_required
    @require_POST
    def _view(request: HttpRequest) -> HttpResponse:
        search_term = request.POST.get(param_name, "").strip()
        results = search_fn(search_term)
        row_template_override = request.POST.get("row_template", "")
        row_template = (
            row_template_override
            if row_template_override.startswith("fundingrequests/partials/")
            else default_row_template
        )
        return render(
            request,
            results_template,
            {
                results_key: results,
                "search_term": search_term,
                "row_template": row_template,
            },
        )

    return _view
