"""The registry-scale facets' dedicated search endpoint.

Typing in a journal/publisher search box must not re-run the funding-request
list query: the whole region render (list rows, chips, pills) is dead weight
for a typeahead. This view answers only the widget: narrowed options plus the
already-selected ones, as the widget template's markup. Selection still goes
through the region request; typing browses, selecting filters.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests.facets import FACET_FIELDS, facet_choices
from coda.apps.widgets import SearchSelectMultiWidget

_PLACEHOLDERS = {"journal": "Select journals", "publisher": "Select publishers"}


@login_required
def facet_options(request: HttpRequest) -> HttpResponse:
    """Render one remote-search select with the query-narrowed options."""
    facet = request.GET.get("facet", "")
    if facet not in FACET_FIELDS:
        raise Http404(f"Unknown facet: {facet}")
    query = request.GET.get("q", "").strip()
    selected = request.GET.getlist("selected")

    widget = SearchSelectMultiWidget(
        attrs={"id": f"id_{facet}", "class": "w-100", "placeholder": _PLACEHOLDERS[facet]}
    )
    widget.remote_search = True
    widget.remote_query = query
    model = FACET_FIELDS[facet]
    widget.choices = facet_choices(model, selected, query)

    return render(
        request,
        "forms/search-select-multi-widget.html",
        {"widget": widget.get_context(facet, selected, {})["widget"]},
    )
