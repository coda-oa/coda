from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

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
    ChipBuilder,
    FilterSummary,
    ListRegionMixin,
    parse_date_filter,
)
from coda.apps.views import EntityListView
from coda.coda_itertools import map_or_none
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
        summary = build_filter_summary(self.request, labels, ctx["contract_list"])

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
            "filter_count": summary.count,
            "filter_errors": summary.errors,
            "date_filter_error": summary.error_for("id_start_date", "id_end_date"),
            "label_state": sorted(_label_ids(self.request.GET.getlist("labels"))),
            "active_filters": summary.chips,
        }


_LISTVIEW_URL = "fundingrequests:list"
_LIST_REGION_URL = "fundingrequests:list_region"


class FundingRequestListRegionView(ListRegionMixin, FundingRequestListView):
    template_name = "fundingrequests/fundingrequest_filtered_list.html"
    region_url_name = _LISTVIEW_URL


fundingrequest_list = FundingRequestListView.as_view()
fundingrequest_list_region = FundingRequestListRegionView.as_view()


def query(request: HttpRequest) -> QuerySet[FundingRequestModel]:
    review_results = [ReviewResult(rr) for rr in request.GET.getlist("processing_status")]
    open_access_types = [OpenAccessType(oat) for oat in request.GET.getlist("open_access_type")]
    requested_payment_statuses = [
        _payment_status_map[status] for status in request.GET.getlist("payment_status")
    ]
    payment_methods = [PaymentMethod(pm) for pm in request.GET.getlist("payment_methods")]
    show_invalid_contract_years = request.GET.get("invalid_contract_years") == "on"
    publication_states = request.GET.getlist("publication_states")
    publication_type = request.GET.get("publication_type") or None
    sort_order = fq.SortOrder.try_parse(request.GET.get("sort_by"))

    params = fq.FundingRequestSearchParams(
        date_range=parse_date_filter(
            request, start_key=_DATE_START_KEY, end_key=_DATE_END_KEY
        ).date_range,
        review_results=review_results,
        payment_statuses=requested_payment_statuses,
        labels=sorted(_label_ids(request.GET.getlist("labels"))),
        exclude_labels=sorted(_label_ids(request.GET.getlist("exclude_labels"))),
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        entity_type=fq.PublicationEntityType.try_parse(publication_type),
        search_term=request.GET.get("search_term", "").strip(),
        contract_id=map_or_none(int, request.GET.get("contract_name")),
        contract_year=map_or_none(int, request.GET.get("contract_year")),
        show_invalid_contract_years=show_invalid_contract_years,
    )

    criteria = fq.build_criteria(params)
    return fq.search(*criteria, sort_order=sort_order)


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


def build_filter_summary(
    request: HttpRequest, labels: Sequence[Label], contracts: Sequence[Contract]
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
    chips.multi("processing_status", "processing_status")
    chips.multi("payment_status", "id_payment_status", labels=dict(_payment_status_choices))
    chips.multi("payment_methods", "payment_methods")
    chips.multi("open_access_type", "open_access_type")

    publication_type = request.GET.get("publication_type")
    if publication_type and publication_type != _DEFAULT_PUBLICATION_TYPE:
        chips.add(
            "publication_type",
            publication_type,
            publication_type.title(),
            f"publication_type_{publication_type}",
        )

    chips.multi(
        "publication_states", "id_publication_states", labels=dict(_publication_state_choices)
    )
    chips.date_range(
        start_key=_DATE_START_KEY,
        end_key=_DATE_END_KEY,
        start_source_id="id_start_date",
        end_source_id="id_end_date",
    )
    chips.single(
        "contract_name",
        "contract_name",
        labels={str(contract.pk): contract.name for contract in contracts},
    )
    chips.single("contract_year", "contract_year", prefix="Year ")
    chips.switch("invalid_contract_years", "Invalid years only", "invalid_contract_years")

    names = {str(label.pk): label.name for label in labels}
    colors = {str(label.pk): label.hexcolor for label in labels}
    for value in request.GET.getlist("labels"):
        if value:
            chips.add(
                "labels",
                value,
                names.get(value, value),
                "label-pills",
                kind="label",
                label_color=colors.get(value),
            )
    for value in request.GET.getlist("exclude_labels"):
        if value:
            chips.add(
                "exclude_labels",
                value,
                f"Not: {names.get(value, value)}",
                "exclude_labels",
                kind="label",
                label_color=colors.get(value),
            )
    return chips.summary()
