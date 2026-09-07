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
from coda.apps.views import EntityListView
from coda.domain.date import DateRange
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState

_advanced_search_fields = [
    "exclude_labels",
    "processing_status",
    "open_access_type",
    "payment_status",
    "start_date",
    "end_date",
    "publication_type",
    "contract_name",
    "contract_year",
    "publication_states",
    "payment_methods",
]

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


@breadcrumb("Funding Requests", parent_url_name="fundingrequests:home")
class FundingRequestListView(LoginRequiredMixin, EntityListView[FundingRequestListItem]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"
    entity_filter_template = "fundingrequests/forms/fundingrequest_filter.html"

    def get_entities(self, request: HttpRequest) -> Sequence[FundingRequestListItem]:
        django_queryset = query(request)
        return LazyBulkQuerySet(
            queryset=django_queryset,
            bulk_converter=list_query.get_list_items,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_contract_list_context())

        expand_advanced_search = any(
            self.request.GET.get(key)
            for key in _advanced_search_fields
            if self.request.GET.get(key) and self.request.GET.get(key) != _default_choices.get(key)
        )

        labels = list(Label.objects.all().order_by("name"))
        publication_types = [(et.value, et.value) for et in fq.PublicationEntityType]
        selected_publication_types = self.request.GET.get("publication_type")

        payment_methods = [(pm.value, pm.value) for pm in PaymentMethod]

        return ctx | {
            "labels": labels,
            "label_pills": build_label_pills(self.request, labels),
            "processing_states": [rr.value for rr in ReviewResult],
            "open_access_types": [oat.value for oat in OpenAccessType],
            "expand_advanced_search": expand_advanced_search,
            "payment_status_choices": _payment_status_choices,
            "publication_types": publication_types,
            "selected_publication_types": selected_publication_types,
            "payment_methods": payment_methods,
            "publication_states": _publication_state_choices,
        }


fundingrequest_list = FundingRequestListView.as_view()


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
        try:
            return map_fn(value)
        except ValueError:
            return None

    return None


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@dataclass(frozen=True)
class LabelPill:
    name: str
    color: str
    state: Literal["default", "included"]
    toggle_url: str


def _label_ids(values: list[str]) -> set[int]:
    """Parse label ids from raw query values, ignoring non-int values."""
    ids = set()
    for value in values:
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return ids


def label_pill_url(request: HttpRequest, *, labels: set[int]) -> str:
    """Build the list URL for a given label filter state.

    Preserves all current GET params except ``labels`` and ``page``, then sets
    the new label list. An empty list is omitted. ``exclude_labels`` is
    managed by the advanced-search.
    """
    params = request.GET.copy()
    params.pop("labels", None)
    params.pop("page", None)
    if labels:
        params.setlist("labels", [str(x) for x in sorted(labels)])
    encoded = params.urlencode()
    path = reverse("fundingrequests:list")
    return f"{path}?{encoded}" if encoded else path


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
        )
        for label in labels
    ]
