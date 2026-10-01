"""Shared view-side mechanics for list pages with an HTMX filter sidebar.

A list page opts in by:
- rendering the shared ``partials/filter_layout.html`` template structure,
- exposing a region view subclassing :class:`ListRegionMixin`,
- summarizing active filters with :class:`ChipBuilder`, whose badge count is the
  number of chips it collected; a filter that rejects its value records a
  :class:`FilterError` — one message plus the control ids it invalidates.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Literal, cast

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.urls import reverse
from django.views.generic import TemplateView

from coda.apps.widgets import DateRangeWidget
from coda.domain.date import DateRange, InvalidDateError, InvalidDateRangeError


class ListSortOrder(StrEnum):
    date_desc = "date_desc"
    date_asc = "date_asc"
    alphabetical = "alphabetical"

    @staticmethod
    def choices() -> tuple[tuple[str, str], ...]:
        return (
            (ListSortOrder.date_desc.value, "Date descending"),
            (ListSortOrder.date_asc.value, "Date ascending"),
            (ListSortOrder.alphabetical.value, "Alphabet"),
        )

    @staticmethod
    def parse_or_default(value: Any) -> "ListSortOrder":
        try:
            return ListSortOrder(value)
        except ValueError:
            return ListSortOrder.date_desc


class ListRegionMixin(TemplateView):
    """Marks a list-region (fragment) view: pushes the canonical list URL on htmx requests."""

    list_url_name: ClassVar[str]

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any) -> HttpResponse:
        response = super().render_to_response(context, **response_kwargs)
        if self.request.headers.get("HX-Request") == "true":
            response["HX-Push-Url"] = self._push_url()
        return response

    def _push_url(self) -> str:
        path = reverse(self.list_url_name)
        if self.request.GET:
            return f"{path}?{self.request.GET.urlencode()}"
        return path


def valid_fields(form: forms.Form) -> dict[str, Any]:
    """The bound form's cleaned fields, minus any the form rejected.

    Cleaning runs per field, so valid fields land in ``cleaned_data`` even when
    others fail; callers drop just the rejected field's effect instead of failing
    the whole request.
    """
    form.is_valid()
    return {name: value for name, value in form.cleaned_data.items() if name not in form.errors}


def named_model_choices(items: Iterable[Any]) -> list[tuple[Any, str]]:
    """Return a blank option followed by choices from named model instances."""
    return [("", "-------"), *((item.pk, item.name) for item in items)]


class DateRangeField(forms.MultiValueField):
    """One date-range value backed by the sidebar's two existing GET params."""

    def __init__(self, *, input_names: tuple[str, str], input_ids: tuple[str, str]) -> None:
        super().__init__(
            (forms.CharField(required=False), forms.CharField(required=False)),
            widget=DateRangeWidget(input_names=input_names, input_ids=input_ids),
            required=False,
            require_all_fields=False,
        )

    def compress(self, data_list: list[str]) -> DateRange | None:
        if not data_list:
            return None
        start, end = data_list
        try:
            return DateRange.from_iso(start=start or None, end=end or None)
        except (InvalidDateError, InvalidDateRangeError) as error:
            cast(DateRangeWidget, self.widget).mark_invalid()
            raise ValidationError(str(error)) from error


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

        ``None``/empty is ignored, so callers can pass a form error straight
        through. First writer wins per control, so a later filter can never
        overwrite a message the user already needs.
        """
        if not message or self._errored_ids.intersection(source_ids):
            return
        self._errored_ids.update(source_ids)
        self._errors.append(FilterError(message=message, source_ids=tuple(source_ids)))

    def date_range(
        self,
        *,
        start_key: str,
        end_key: str,
        start_source_id: str,
        end_source_id: str,
        date_range: DateRange | None,
        error: str | None,
    ) -> None:
        """Build chips from the form's validated range or record its rejection."""
        self.error(error, start_source_id, end_source_id)
        if date_range is None:
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
