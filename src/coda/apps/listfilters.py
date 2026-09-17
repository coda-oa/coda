"""Shared view-side mechanics for list pages with an HTMX filter sidebar.

A list page opts in by:
- rendering the shared ``partials/filter_layout.html`` template structure,
- exposing a region view subclassing :class:`ListRegionMixin`,
- counting its active filters via :func:`count_active_filters`,
- building removable chips from :class:`ActiveFilter` and :func:`remove_value_url`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views.generic import TemplateView


class ListRegionMixin(TemplateView):
    """Marks a list-region (fragment) view: pushes the canonical list URL on htmx requests."""

    region_url_name: str

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        response = super().render_to_response(context, **response_kwargs)
        if self.request.headers.get("HX-Request") == "true":
            response["HX-Push-Url"] = self._push_url()
        return response

    def _push_url(self) -> str:
        path = reverse(self.region_url_name)
        if self.request.GET:
            return f"{path}?{self.request.GET.urlencode()}"
        return path


def count_active_filters(
    request: HttpRequest,
    *,
    multi_value_fields: Sequence[str] = (),
    single_value_fields: Sequence[str] = (),
    default_choices: Mapping[str, str] | None = None,
) -> int:
    """Number of active filter values across the given field names.

    Every occurrence of a ``multi_value_fields`` key counts, each non-empty
    ``single_value_fields`` key counts once, and a key in ``default_choices``
    counts only when present with a value other than its default.
    """
    count = sum(len(request.GET.getlist(key)) for key in multi_value_fields)
    count += sum(1 for key in single_value_fields if request.GET.get(key))
    for key, default in (default_choices or {}).items():
        if request.GET.get(key) not in (None, default):
            count += 1
    return count


@dataclass(frozen=True)
class ActiveFilter:
    text: str
    remove_url: str
    remove_fragment_url: str
    source_id: str
    kind: Literal["neutral", "label"]
    label_color: str | None


def remove_value_url(request: HttpRequest, url_name: str, *, key: str, value: str | None) -> str:
    """List URL without one value of ``key``; other params preserved, ``page`` dropped.

    ``value=None`` removes the whole key (single-value fields). For multi-value
    keys one occurrence is dropped and the remaining order preserved; an emptied
    key is omitted entirely.
    """
    params = request.GET.copy()
    params.pop("page", None)
    if value is None:
        params.pop(key, None)
    else:
        remaining = list(params.getlist(key))
        if value in remaining:
            remaining.remove(value)
        if remaining:
            params.setlist(key, remaining)
        else:
            params.pop(key, None)
    encoded = params.urlencode()
    path = reverse(url_name)
    return f"{path}?{encoded}" if encoded else path
