from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import LazyBulkQuerySet
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.queries import list as list_query
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.apps.listfilters import (
    ActiveFilter,
    ListRegionMixin,
    count_active_filters,
    remove_value_url,
)
from coda.apps.views import EntityListView
from coda.domain.date import DateRange
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState

_payment_status_map = {
    "paid": fq.PaymentStatus.Paid,
    "unpaid": fq.PaymentStatus.Unpaid,
    "invoice_received": fq.PaymentStatus.InvoiceReceived,
    "covered_by_contract": fq.PaymentStatus.CoveredByContract,
}

_payment_status_choices = [
    ("paid", "Paid"),
    ("unpaid", "Unpaid"),
    ("invoice_received", "Invoice Received"),
    ("covered_by_contract", "Covered by Contract"),
]

_publication_state_choices = [
    ("Published", "Published"),
    *((s.name, s.value) for s in UnpublishedState),
]

_default_choices = {"publication_type": "all"}

_multi_value_fields = (
    "labels",
    "exclude_labels",
    "processing_status",
    "open_access_type",
    "payment_status",
    "payment_methods",
    "publication_states",
)

_single_value_fields = (
    "start_date",
    "end_date",
    "contract_name",
    "contract_year",
    "invalid_contract_years",
)


def filter_count(request: HttpRequest) -> int:
    return count_active_filters(
        request,
        multi_value_fields=_multi_value_fields,
        single_value_fields=_single_value_fields,
        default_choices=_default_choices,
    )


@breadcrumb("Funding Requests", parent_url_name="fundingrequests:home")
class FundingRequestListView(LoginRequiredMixin, EntityListView[FundingRequestListItem]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"

    def get_entities(self, request: HttpRequest) -> Sequence[FundingRequestListItem]:
        django_queryset = query(request)
        return LazyBulkQuerySet(
            queryset=django_queryset,
            bulk_converter=list_query.get_list_items,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_contract_list_context())

        labels = list(Label.objects.all().order_by("name"))
        publication_types = [(et.value, et.value.title()) for et in fq.PublicationEntityType]
        selected_publication_types = self.request.GET.get("publication_type")

        payment_methods = [(pm.value, pm.value) for pm in PaymentMethod]

        return ctx | {
            "labels": labels,
            "label_pills": build_label_pills(self.request, labels),
            "processing_states": [rr.value for rr in ReviewResult],
            "open_access_types": [oat.value for oat in OpenAccessType],
            "payment_status_choices": _payment_status_choices,
            "publication_types": publication_types,
            "selected_publication_types": selected_publication_types,
            "payment_methods": payment_methods,
            "publication_states": _publication_state_choices,
            "filter_count": filter_count(self.request),
            "label_state": sorted(_label_ids(self.request.GET.getlist("labels"))),
            "active_filters": build_active_filters(self.request, labels, ctx["contract_list"]),
        }


class FundingRequestListRegionView(ListRegionMixin, FundingRequestListView):
    template_name = "fundingrequests/fundingrequest_filtered_list.html"
    region_url_name = "fundingrequests:list"


fundingrequest_list = FundingRequestListView.as_view()
fundingrequest_list_region = FundingRequestListRegionView.as_view()


def query(request: HttpRequest) -> QuerySet[FundingRequestModel]:
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    review_results = [ReviewResult(rr) for rr in request.GET.getlist("processing_status")]
    open_access_types = [OpenAccessType(oat) for oat in request.GET.getlist("open_access_type")]
    requested_payment_statuses = [
        _payment_status_map[status] for status in request.GET.getlist("payment_status")
    ]
    payment_methods = [PaymentMethod(pm) for pm in request.GET.getlist("payment_methods")]
    show_invalid_contract_years = request.GET.get("invalid_contract_years") == "on"
    publication_states = request.GET.getlist("publication_states")

    try:
        date_range = DateRange.try_fromisoformat(
            start=start_date,
            end=end_date,
        )
    except ValueError as e:
        messages.warning(request, str(e))
        return fq.search()

    params = fq.FundingRequestSearchParams(
        date_range=date_range,
        review_results=review_results,
        payment_statuses=requested_payment_statuses,
        labels=sorted(_label_ids(request.GET.getlist("labels"))),
        exclude_labels=sorted(_label_ids(request.GET.getlist("exclude_labels"))),
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        entity_type=fq.PublicationEntityType.try_parse(request.GET.get("publication_type")),
        search_term=request.GET.get("search_term", "").strip(),
        contract_id=map_or_none(int, request.GET.get("contract_name")),
        contract_year=map_or_none(int, request.GET.get("contract_year")),
        show_invalid_contract_years=show_invalid_contract_years,
    )

    criteria = fq.build_criteria(params)
    return fq.search(*criteria)


def map_or_none[T](map_fn: Callable[[str], T], value: str | None) -> T | None:
    if value:
        return map_fn(value)

    return None


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@dataclass(frozen=True)
class LabelPill:
    name: str
    color: str
    state: Literal["default", "included"]
    toggle_url: str
    toggle_fragment_url: str


def _label_ids(values: list[str]) -> set[int]:
    """Parse label ids from raw query values, ignoring non-int values."""
    ids = set()
    for value in values:
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return ids


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
    return _pill_url(request, "fundingrequests:list", labels=labels)


def label_pill_fragment_url(request: HttpRequest, *, labels: set[int]) -> str:
    """List-region variant of `label_pill_url` for in-place list updates."""
    return _pill_url(request, "fundingrequests:list_region", labels=labels)


def build_label_pills(request: HttpRequest, labels: Sequence[Label]) -> list[LabelPill]:
    """Build one pill per label, reflecting the current ``labels`` filter.

    A label in the ``labels`` query param renders as ``included`` and its
    toggle link removes it; every other label renders as ``default`` and its
    toggle link adds it.
    """
    included = _label_ids(request.GET.getlist("labels"))
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


def build_active_filters(
    request: HttpRequest, labels: Sequence[Label], contracts: Sequence[Contract]
) -> list[ActiveFilter]:
    """One removable chip per active filter value, matching ``filter_count``.

    Order mirrors the rail's group order. Text is the bare value except where
    that would be ambiguous (dates, contract year, excluded labels, switch).
    Unknown ids (stale URLs) fall back to the raw value.
    """

    def add(
        key: str,
        value: str | None,
        text: str,
        source_id: str,
        kind: Literal["neutral", "label"] = "neutral",
        label_color: str | None = None,
    ) -> None:
        chips.append(
            ActiveFilter(
                text=text,
                remove_url=remove_value_url(request, "fundingrequests:list", key=key, value=value),
                remove_fragment_url=remove_value_url(
                    request, "fundingrequests:list_region", key=key, value=value
                ),
                source_id=source_id,
                kind=kind,
                label_color=label_color,
            )
        )

    chips: list[ActiveFilter] = []

    for value in request.GET.getlist("processing_status"):
        add("processing_status", value, value, "processing_status")

    payment_labels = dict(_payment_status_choices)
    for value in request.GET.getlist("payment_status"):
        add("payment_status", value, payment_labels.get(value, value), "id_payment_status")

    for value in request.GET.getlist("payment_methods"):
        add("payment_methods", value, value, "payment_methods")

    for value in request.GET.getlist("open_access_type"):
        add("open_access_type", value, value, "open_access_type")

    publication_type = request.GET.get("publication_type")
    if publication_type and publication_type != _default_choices["publication_type"]:
        add(
            "publication_type",
            publication_type,
            publication_type.title(),
            f"publication_type_{publication_type}",
        )

    publication_state_labels = dict(_publication_state_choices)
    for value in request.GET.getlist("publication_states"):
        add(
            "publication_states",
            value,
            publication_state_labels.get(value, value),
            f"publication-state-{value}",
        )

    start_date = request.GET.get("start_date")
    if start_date:
        add("start_date", start_date, f"From {start_date}", "id_start_date")

    end_date = request.GET.get("end_date")
    if end_date:
        add("end_date", end_date, f"To {end_date}", "id_end_date")

    contract_names = {str(contract.pk): contract.name for contract in contracts}
    contract = request.GET.get("contract_name")
    if contract:
        add("contract_name", contract, contract_names.get(contract, contract), "contract_name")

    contract_year = request.GET.get("contract_year")
    if contract_year:
        add("contract_year", contract_year, f"Year {contract_year}", "contract_year")

    if request.GET.get("invalid_contract_years"):
        add("invalid_contract_years", None, "Invalid years only", "invalid_contract_years")

    label_index = {str(label.pk): label for label in labels}
    for value in request.GET.getlist("labels"):
        label = label_index.get(value)
        add(
            "labels",
            value,
            label.name if label else value,
            "label-pills",
            kind="label",
            label_color=label.hexcolor if label else None,
        )
    for value in request.GET.getlist("exclude_labels"):
        label = label_index.get(value)
        add(
            "exclude_labels",
            value,
            f"Not: {label.name}" if label else f"Not: {value}",
            "exclude_labels",
            kind="label",
            label_color=label.hexcolor if label else None,
        )

    return chips
