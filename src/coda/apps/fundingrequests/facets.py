"""The registry-scale facets: choices narrowing and the remote-search wiring.

Journal and publisher cannot enumerate every option server-side. The widget's
choices narrow to the query's matches plus the already-selected values; the
search term round-trips through the ``<name>_q`` hidden input the widget
renders, so both the facet-options endpoint and the region request keep the
narrowing alive.
"""

import functools
from collections.abc import Iterable
from typing import Any

from django import forms
from django.utils.datastructures import MultiValueDict

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.apps.widgets import SearchSelectMultiWidget, remote_query_key

#: Registry-scale facets: the form field name and the model attribute the
#: options are labelled with.
FACET_FIELDS: dict[str, type[Journal] | type[Publisher]] = {
    "journal": Journal,
    "publisher": Publisher,
}

_FACET_CHOICE_LIMIT = 100


def _selected_pks(selected: Iterable[str]) -> list[int]:
    """The numeric selection; runs during form construction, before field
    validation - garbage in the URL (a crafted ``?journal=²`` or ``['abc']``)
    must narrow nothing, not crash the view; the field reports the error."""
    pks = []
    for value in selected:
        try:
            pks.append(int(value))
        except (TypeError, ValueError):
            continue
    return pks


def facet_choices(
    model: type[Journal] | type[Publisher],
    selected: Iterable[str],
    query: str,
) -> list[tuple[Any, str]]:
    """The rendered choices for a registry-scale facet: the first
    ``_FACET_CHOICE_LIMIT`` matches of ``query`` in alphabetical order, plus
    every already-selected row (which may fall outside that cap). Enumerating
    the whole registry instead blows up the rail on real data volumes.
    """
    label_field = model.facet_label_field
    matches = (
        model.objects.filter(**{f"{label_field}__icontains": query})
        if query
        else model.objects.all()
    )
    choices = [
        (obj.pk, str(getattr(obj, label_field)))
        for obj in matches.order_by(label_field)[:_FACET_CHOICE_LIMIT]
    ]
    shown = {pk for pk, _ in choices}
    selected_pks = _selected_pks(selected)
    missing = model.objects.filter(pk__in=selected_pks).exclude(pk__in=shown)
    choices += [(obj.pk, str(getattr(obj, label_field))) for obj in missing]
    return choices


def bind_remote_search(
    field: forms.Field, name: str, data: MultiValueDict[str, list[str]] | None, endpoint: str
) -> None:
    """Wire a facet field for remote search: the widget renders the hidden
    input named by ``remote_query_key(name)``, fetches options from
    ``endpoint``, and the choices callable narrows by the submitted term.
    Lazy like the choice lambdas it replaces: form instantiation must not
    hit the database."""
    model = FACET_FIELDS[name]
    query = str(data.get(remote_query_key(name), "")).strip() if data is not None else ""
    widget = field.widget
    assert isinstance(widget, SearchSelectMultiWidget)
    widget.remote_search = True
    widget.remote_query = query
    widget.remote_endpoint = f"{endpoint}?facet={name}"
    selected: list[str] = [str(v) for v in data.getlist(name)] if data is not None else []
    assert isinstance(field, forms.TypedMultipleChoiceField)
    field.choices = functools.partial(facet_choices, model, selected, query)
