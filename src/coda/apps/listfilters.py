"""Shared view-side mechanics for list pages with an HTMX filter sidebar.

A list page opts in by:
- rendering the shared ``partials/filter_layout.html`` template structure,
- exposing a region view subclassing :class:`ListRegionMixin`,
- summarizing active filters with :class:`ChipBuilder`, whose badge count is the
  number of chips it collected; a filter that rejects its value records a
  :class:`FilterError` — one message plus the control ids it invalidates.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from django.http import HttpRequest, HttpResponse, QueryDict
from django.urls import reverse
from django.views.generic import TemplateView

from coda.domain.date import DateRange, InvalidDateError, InvalidDateRangeError


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


@dataclass(frozen=True)
class DateFilter:
    """The sidebar's date-range filter: the range to apply, or why it is dropped."""

    date_range: DateRange | None
    error: str | None


def parse_date_filter(request: HttpRequest, *, start_key: str, end_key: str) -> DateFilter:
    """Read the sidebar's two date params into a range, or one line of error copy."""
    raw_start = (request.GET.get(start_key) or "").strip()
    raw_end = (request.GET.get(end_key) or "").strip()
    if not raw_start and not raw_end:
        return DateFilter(date_range=None, error=None)
    try:
        date_range = DateRange.from_iso(start=raw_start, end=raw_end)
    except (InvalidDateError, InvalidDateRangeError) as error:
        return DateFilter(date_range=None, error=str(error))
    return DateFilter(date_range=date_range, error=None)


@dataclass(frozen=True)
class ActiveFilter:
    text: str
    remove_url: str
    remove_fragment_url: str
    kind: Literal["neutral", "label"]
    label_color: str | None


@dataclass(frozen=True)
class FilterError:
    """A filter value the sidebar rejected: the message, and the controls it invalidates."""

    message: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class FilterSummary:
    """The sidebar's active-filter summary: removable chips, the badge count, rejections.

    ``errors`` is a list, not a single message, because any filter can reject a
    value; each entry names the control ids it invalidates, so a template can mark
    the right input invalid without a second vocabulary. ``date_range`` is the
    only producer today.
    """

    chips: list[ActiveFilter]
    count: int
    errors: list[FilterError]

    def error_for(self, *source_ids: str) -> str | None:
        """The message recorded against any of these controls, None when there is none."""
        for error in self.errors:
            if set(source_ids).intersection(error.source_ids):
                return error.message
        return None


class ChipBuilder:
    """Collect one removable chip per active sidebar filter, in sidebar order.

    The badge count is the number of chips collected, so it cannot drift from the
    chip row: a filter that renders no chip is not counted either. A filter that
    rejects its value records a :class:`FilterError` with :meth:`error` instead of a
    chip; :meth:`date_range` is the only one that does so today, so call it even when
    neither date is filled.
    """

    def __init__(self, request: HttpRequest, *, list_url_name: str, region_url_name: str) -> None:
        self._request = request
        self._list_url_name = list_url_name
        self._region_url_name = region_url_name
        self._chips: list[ActiveFilter] = []
        self._errors: list[FilterError] = []
        self._errored_ids: set[str] = set()

    def add(
        self,
        key: str,
        value: str | None,
        text: str,
        *,
        kind: Literal["neutral", "label"] = "neutral",
        label_color: str | None = None,
    ) -> None:
        """Append one chip. ``value=None`` drops the whole key (checkbox filters)."""
        self._chips.append(
            ActiveFilter(
                text=text,
                remove_url=remove_value_url(
                    self._request, self._list_url_name, key=key, value=value
                ),
                remove_fragment_url=remove_value_url(
                    self._request, self._region_url_name, key=key, value=value
                ),
                kind=kind,
                label_color=label_color,
            )
        )

    def single(
        self,
        key: str,
        *,
        prefix: str = "",
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Chip for a single-valued param: ``prefix`` + looked-up name, raw value as fallback."""
        value = self._request.GET.get(key)
        if value:
            self.add(key, value, prefix + (labels or {}).get(value, value))

    def multi(self, key: str, *, labels: Mapping[str, str] | None = None) -> None:
        """One chip per value of a multi-valued param; an empty value is no filter."""
        for value in self._request.GET.getlist(key):
            if value:
                self.add(key, value, (labels or {}).get(value, value))

    def switch(self, key: str, text: str) -> None:
        """Chip for a checkbox filter: one fixed text, removal drops the key."""
        if self._request.GET.get(key):
            self.add(key, None, text)

    def error(self, message: str | None, *source_ids: str) -> None:
        """Record a rejected filter value and the sidebar controls it invalidates.

        ``None``/empty is ignored, so a caller can pass a parse result straight
        through. First writer wins per control, so a later filter can never
        overwrite a message the user already needs.
        """
        if not message or self._errored_ids.intersection(source_ids):
            return
        self._errored_ids.update(source_ids)
        self._errors.append(FilterError(message=message, source_ids=tuple(source_ids)))

    def date_range(
        self, *, start_key: str, end_key: str, start_source_id: str, end_source_id: str
    ) -> None:
        """Chips for the two date params, only when the range parses.

        A parse failure contributes no chip and records one error against both date
        controls instead — both inputs are invalid, and today's markup marks both.
        """
        parsed = parse_date_filter(self._request, start_key=start_key, end_key=end_key)
        self.error(parsed.error, start_source_id, end_source_id)
        if parsed.date_range is None:
            return

        for key, prefix in ((start_key, "From "), (end_key, "To ")):
            value = self._request.GET.get(key)
            if value:
                self.add(key, value, f"{prefix}{value}")

    def summary(self) -> FilterSummary:
        return FilterSummary(chips=self._chips, count=len(self._chips), errors=self._errors)


def build_url(url_name: str, params: QueryDict) -> str:
    encoded = params.urlencode()
    path = reverse(url_name)
    return f"{path}?{encoded}" if encoded else path


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
        return build_url(url_name, params)

    remaining = list(params.getlist(key))
    if value in remaining:
        remaining.remove(value)

    if remaining:
        params.setlist(key, remaining)
    else:
        params.pop(key, None)

    return build_url(url_name, params)
