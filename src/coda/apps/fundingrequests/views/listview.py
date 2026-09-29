from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import LazyBulkQuerySet
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.forms import (
    FundingRequestListFilterForm,
    parse_label_ids,
    payment_status_choices,
    publication_state_choices,
)
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.queries import list as list_query
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.apps.listfilters import (
    ChipBuilder,
    FilterSummary,
    ListRegionMixin,
)
from coda.apps.views import EntityListView
from coda.domain.date import DateRange

_DEFAULT_PUBLICATION_TYPE = "all"


_DATE_START_KEY = "start_date"
_DATE_END_KEY = "end_date"


@breadcrumb("Funding Requests", parent_url_name="fundingrequests:home")
class FundingRequestListView(LoginRequiredMixin, EntityListView[FundingRequestListItem]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"

    def get_entities(self, request: HttpRequest) -> Sequence[FundingRequestListItem]:
        filter_form = FundingRequestListFilterForm(request.GET)
        criteria, sort_order = filter_form.search_criteria()
        django_queryset = fq.search(*criteria, sort_order=fq.SortOrder[sort_order.name])
        return LazyBulkQuerySet(
            queryset=django_queryset,
            bulk_converter=list_query.get_list_items,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_contract_list_context())

        labels = list(Label.objects.all().order_by("name"))
        filter_form = FundingRequestListFilterForm(
            self.request.GET,
            contracts=ctx["contract_list"],
            labels=labels,
        )
        filter_form.is_valid()
        date_errors = filter_form.errors.get("date_range")
        date_range_error = str(date_errors[0]) if date_errors else None
        summary = build_filter_summary(
            self.request,
            labels,
            ctx["contract_list"],
            date_range=filter_form.cleaned_data.get("date_range"),
            date_range_error=date_range_error,
        )

        return ctx | {
            "labels": labels,
            "label_pills": build_label_pills(self.request, labels),
            "filter_count": summary.count,
            "filter_errors": summary.errors,
            "label_state": sorted(parse_label_ids(self.request.GET.getlist("labels"))),
            "active_filters": summary.chips,
            "filter_form": filter_form,
        }


_LISTVIEW_URL = "fundingrequests:list"
_LIST_REGION_URL = "fundingrequests:list_region"


class FundingRequestListRegionView(ListRegionMixin, FundingRequestListView):
    template_name = "fundingrequests/fundingrequest_filtered_list.html"
    list_url_name = _LISTVIEW_URL


fundingrequest_list = FundingRequestListView.as_view()
fundingrequest_list_region = FundingRequestListRegionView.as_view()


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@dataclass(frozen=True)
class LabelPill:
    name: str
    color: str
    state: Literal["default", "included"]
    toggle_url: str
    toggle_fragment_url: str


def _pill_url(request: HttpRequest, url_name: str, *, labels: set[int]) -> str:
    params = request.GET.copy()
    params.pop("labels", None)
    params.pop("page", None)
    if labels:
        params.setlist("labels", [str(x) for x in sorted(labels)])
    encoded = params.urlencode()
    path = reverse(url_name)
    return f"{path}?{encoded}" if encoded else path


def label_pill_url(request: HttpRequest, *, labels: set[int]) -> str:
    """Build the list URL for a given label filter state.

    Preserves all current GET params except ``labels`` and ``page``, then sets
    the new label list. An empty list is omitted. ``exclude_labels`` is
    managed by the advanced-search.
    """
    return _pill_url(request, _LISTVIEW_URL, labels=labels)


def label_pill_fragment_url(request: HttpRequest, *, labels: set[int]) -> str:
    """List-region variant of `label_pill_url` for in-place list updates."""
    return _pill_url(request, _LIST_REGION_URL, labels=labels)


def build_label_pills(request: HttpRequest, labels: Sequence[Label]) -> list[LabelPill]:
    """Build one pill per label, reflecting the current ``labels`` filter.

    A label in the ``labels`` query param renders as ``included`` and its
    toggle link removes it; every other label renders as ``default`` and its
    toggle link adds it.
    """
    included = parse_label_ids(request.GET.getlist("labels"))
    return [
        LabelPill(
            name=label.name,
            color=label.hexcolor,
            state="included" if label.pk in included else "default",
            toggle_url=label_pill_url(request, labels=included ^ {label.pk}),
            toggle_fragment_url=label_pill_fragment_url(request, labels=included ^ {label.pk}),
        )
        for label in labels
    ]


def build_filter_summary(
    request: HttpRequest,
    labels: Sequence[Label],
    contracts: Sequence[Contract],
    *,
    date_range: DateRange | None,
    date_range_error: str | None,
) -> FilterSummary:
    """One removable chip per active filter value, in the rail's group order.

    Text is the bare value except where that would be ambiguous (dates, contract
    year, excluded labels, switch). Unknown ids (stale URLs) fall back to the raw
    value.
    """
    chips = ChipBuilder(
        request,
        list_url_name=_LISTVIEW_URL,
        region_url_name=_LIST_REGION_URL,
    )
    chips.multi("processing_status")
    chips.multi("payment_status", labels=dict(payment_status_choices))
    chips.multi("payment_methods")
    chips.multi("open_access_type")

    publication_type = request.GET.get("publication_type")
    if publication_type and publication_type != _DEFAULT_PUBLICATION_TYPE:
        chips.add("publication_type", publication_type, publication_type.title())

    chips.multi("publication_states", labels=dict(publication_state_choices))
    chips.date_range(
        start_key=_DATE_START_KEY,
        end_key=_DATE_END_KEY,
        start_source_id="id_start_date",
        end_source_id="id_end_date",
        date_range=date_range,
        error=date_range_error,
    )
    chips.single(
        "contract_name",
        labels={str(contract.pk): contract.name for contract in contracts},
    )
    chips.single("contract_year", prefix="Year ")
    chips.switch("invalid_contract_years", "Invalid years only")

    names = {str(label.pk): label.name for label in labels}
    colors = {str(label.pk): label.hexcolor for label in labels}
    for value in request.GET.getlist("labels"):
        if value:
            chips.add(
                "labels",
                value,
                names.get(value, value),
                kind="label",
                label_color=colors.get(value),
            )
    for value in request.GET.getlist("exclude_labels"):
        if value:
            chips.add(
                "exclude_labels",
                value,
                f"Not: {names.get(value, value)}",
                kind="label",
                label_color=colors.get(value),
            )
    return chips.summary()
