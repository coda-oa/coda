import datetime
from collections.abc import Sequence
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import repository
from coda.apps.invoices.models import Creditor
from coda.apps.publications.models import Publication
from coda.apps.views import EntityListView
from coda.contract import ContractYear
from coda.date import DateRange
from coda.invoice import FundingSourceId, Invoice, InvoiceId, ItemType, PaymentStatus, Position
from coda.money import Money
from coda.publication import PublicationId


class InvoiceListView(LoginRequiredMixin, EntityListView["InvoiceViewModel"]):
    paginate_by = 20
    entity_name = "Invoices"
    entity_create_url = "invoices:create"
    entity_list_item_template = "invoices/invoice_list_item.html"
    entity_filter_template = "invoices/invoice_filter_bar.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["payment_statuses"] = [p.value for p in PaymentStatus]
        return ctx

    def get_entities(self, request: HttpRequest) -> Sequence["InvoiceViewModel"]:
        query: dict[str, Any] = {}
        query["invoice_number"] = request.GET.get("invoice_number")
        query["creditor"] = request.GET.get("creditor")

        if status := request.GET.get("payment_status"):
            query["status"] = self.try_into_paymentstatus(status)

        query["date_range"] = DateRange.try_fromisoformat(
            start=request.GET.get("date_start"),
            end=request.GET.get("date_end"),
        )

        return list(invoice_viewmodel(i) for i in repository.search(**query))

    def try_into_paymentstatus(self, status: str) -> PaymentStatus | None:
        try:
            return PaymentStatus(status)
        except ValueError:
            return None


invoice_list = InvoiceListView.as_view()


@login_required
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    return render(request, "invoices/detail.html", {"invoice": invoice_viewmodel(invoice)})


def invoice_viewmodel(invoice: Invoice) -> "InvoiceViewModel":
    creditor_name = Creditor.objects.get(id=invoice.creditor).name
    id = cast(InvoiceId, invoice.id)
    url = reverse("invoices:detail", kwargs={"pk": id})
    return InvoiceViewModel(
        id=id,
        url=url,
        status=invoice.status.name,
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        creditor_name=creditor_name,
        positions=[
            position_viewmodel(position, i) for i, position in enumerate(invoice.positions, start=1)
        ],
        tax=invoice.tax(),
        total=invoice.total(),
    )


def position_viewmodel(position: Position[ItemType], number: int) -> "PositionViewModel":
    match position.item:
        case ContractYear() as contract_year:
            contract = contract_year.contract
            position_name = str(contract.name)
            submitter = ""
            related_funding_request = None
        case PublicationId(pub_id):
            publication = get_object_or_404(Publication, pk=pub_id)
            position_name = publication.title
            submitter = cast(Author, publication.submitting_author).name
            related_request = FundingRequest.objects.filter(publication_id=position.item).first()
            related_funding_request = None
            if related_request:
                related_funding_request = FundingRequestViewModel(
                    url=related_request.get_absolute_url(),
                    request_id=related_request.request_id,
                )
        case str(description):
            position_name = description
            submitter = ""
            related_funding_request = None

    return PositionViewModel(
        number=str(number),
        name=position_name,
        publication_submitter=submitter,
        cost=position.cost,
        cost_type=position.cost_type.value,
        related_funding_request=related_funding_request,
        funding_source_id=position.funding_source,
    )


class FundingRequestViewModel(NamedTuple):
    url: str
    request_id: str


class PositionViewModel(NamedTuple):
    number: str
    name: str
    publication_submitter: str
    cost: Money
    cost_type: str
    related_funding_request: FundingRequestViewModel | None
    funding_source_id: FundingSourceId | None


class InvoiceViewModel(NamedTuple):
    id: int
    url: str
    status: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    positions: list[PositionViewModel]
    tax: Money
    total: Money
