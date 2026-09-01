"""Display helpers for the filters persisted on export/report rows.

Raw ``filters`` JSON is read through :class:`ExportFiltersDto`, which
validates and decodes it (including the legacy comma-joined formats), so the
projection below only deals with typed values.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, get_args, get_origin
from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
)
from coda.apps.fundingrequests.fundingrequest_query import PublicationEntityType
from coda.apps.invoices.models import FundingSource
from coda.contexts.exports.dto.filters import ExportFiltersDto
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import DecimalSeparator
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState


def _is_multi_value(annotation: Any) -> bool:
    return any(get_origin(arg) is list for arg in get_args(annotation))


MULTI_VALUE_FILTER_FIELDS = {
    name
    for name, field in ExportFiltersDto.model_fields.items()
    if _is_multi_value(field.annotation)
}
SINGLE_VALUE_FILTER_FIELDS = set(ExportFiltersDto.model_fields) - MULTI_VALUE_FILTER_FIELDS


def filter_field_label(field_name: str) -> str:
    """Human-readable label for a filter field, falling back to its name."""
    model_field = ExportFiltersDto.model_fields.get(field_name)
    if model_field is not None and model_field.title:
        return str(model_field.title)
    return field_name


def parse_current_filters_to_context(request: HttpRequest) -> dict[str, str | list[str]]:
    filters: dict[str, str | list[str]] = {}
    for key in MULTI_VALUE_FILTER_FIELDS:
        values = request.GET.getlist(key)
        if values:
            filters[key] = values
    for key in SINGLE_VALUE_FILTER_FIELDS:
        values = request.GET.getlist(key)
        if values:
            filters[key] = values[0]
    return filters


# ---------------------------------------------------------------------------
# Shared choice lists used in both filter forms.
# ---------------------------------------------------------------------------
publication_state_choices: list[tuple[str, str]] = [
    ("Published", "Published"),
    *((s.name, s.value) for s in UnpublishedState),
]

payment_status_choices: list[tuple[str, str]] = [
    (status.value, status.value.replace("_", " ").title()) for status in FundingRequestPaymentStatus
]


def build_filter_form_context() -> dict[str, object]:
    """Return the template context dict needed to render any filter form.

    Both the CSV export form and the openCost generate form use exactly the
    same set of filter widgets, so the context they need is identical.
    """
    return {
        "processing_states": [rr.value for rr in ReviewResult],
        "payment_methods": [(pm.value, pm.value) for pm in PaymentMethod],
        "open_access_types": [oat.value for oat in OpenAccessType],
        "publication_states": publication_state_choices,
        "labels": Label.objects.all(),
        "funding_sources": FundingSource.objects.filter(type="budget"),
        "publication_types": [(et.value, et.value) for et in PublicationEntityType],
        "contract_list": Contract.objects.all(),
        "payment_status_choices": payment_status_choices,
        "decimal_separator_choices": [
            (member.value, member.display) for member in DecimalSeparator
        ],
    }


def create_redo_url(filters: dict[str, Any], url_name: str) -> str:
    """Rebuild the filter form URL for 'reuse filters', keys normalized via the DTO."""
    params = ExportFiltersDto.model_validate(filters).to_storage()
    return reverse(url_name) + "?" + urlencode(params, doseq=True)


@dataclass
class AppliedFilter:
    label: str
    value: str


_PERIOD_LABEL = "Period"
_PERIOD_DATE_FORMAT = "%B %-d, %Y"


def _values_text(value: Any) -> str:
    items = value if isinstance(value, list) else [value]
    return ", ".join(item.value if isinstance(item, Enum) else str(item) for item in items)


def _names(names: Any) -> str:
    return ", ".join(names)


_FORMATTERS: dict[str, Callable[[Any], str]] = {
    "payment_status": lambda statuses: ", ".join(
        status.value.replace("_", " ").title() for status in statuses
    ),
    "decimal_separator": lambda separator: separator.display,
    "labels": lambda ids: _names(
        Label.objects.filter(id__in=list(ids)).values_list("name", flat=True)
    ),
    "exclude_labels": lambda ids: _names(
        Label.objects.filter(id__in=list(ids)).values_list("name", flat=True)
    ),
    "contract_name": lambda pk: _names(
        Contract.objects.filter(pk=pk).values_list("name", flat=True)
    ),
    "funding_source": lambda pk: _names(
        FundingSource.objects.filter(pk=pk).values_list("name", flat=True)
    ),
}

# ``period_start`` renders the combined Period row; ``period_end`` is covered by it.
_NOT_DISPLAYED = {"period_end"}


def build_applied_filters(filters: dict[str, Any]) -> list[AppliedFilter]:
    """Project a persisted filter dict into ordered, human-readable rows.

    A row is emitted per applied criterion (unset criteria are skipped);
    unknown keys in the raw dict are ignored. Field declaration order of
    ``ExportFiltersDto`` determines the display order.
    """
    dto = ExportFiltersDto.model_validate(filters)
    applied: list[AppliedFilter] = []
    for name in ExportFiltersDto.model_fields:
        value = getattr(dto, name)
        if name in _NOT_DISPLAYED or not value:
            continue
        if name == "period_start":
            if dto.period_end is None:  # pragma: no cover -- persisted rows always store both
                continue
            start = dto.period_start.strftime(_PERIOD_DATE_FORMAT)  # type: ignore[union-attr]
            end = dto.period_end.strftime(_PERIOD_DATE_FORMAT)
            applied.append(AppliedFilter(label=_PERIOD_LABEL, value=f"{start} to {end}"))
            continue
        formatter = _FORMATTERS.get(name, _values_text)
        applied.append(AppliedFilter(label=filter_field_label(name), value=formatter(value)))
    return applied
