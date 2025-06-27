import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import repository
from coda.apps.invoices.models import Creditor

from coda.apps.invoices.views.positions import (
    to_position_dto,
)

from coda.apps.invoices.views.create import _DefaultContext

from coda.apps.invoices.views.position_list import (
    funding_sources_context,
)

from coda.apps.publications.models import Publication
from coda.apps.views import EntityListView
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.invoice import (
    FundingSourceId,
    Invoice,
    InvoiceId,
    ItemType,
    PaymentStatus,
    Position,
)
from coda.domain.money import Money
from coda.domain.money._currency import Currency
from coda.domain.publication import PublicationId


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
@require_GET
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    display_currency = Currency.from_code(
        request.GET.get("display_currency", invoice.currency().code)
    )
    display_invoice = invoice.convert(display_currency)
    position_list = [to_position_dto(position) for position in display_invoice.positions]
    ext_inv_id = invoice.external_invoice_id
    comment = invoice.comment
    return render(
        request,
        "invoices/detail.html",
        _DefaultContext
        | funding_sources_context()
        | {
            "invoice": invoice_viewmodel(invoice),
            "conversions": invoice.conversions(),
            "display_currency": display_currency,
            "display_invoice": invoice_viewmodel(display_invoice),
            "positions": position_list,
            "external_invoice_id": ext_inv_id,
            "invoice_comment": comment,
        },
    )


@login_required
@require_POST
def add_conversion_dialog(request: HttpRequest, pk: int) -> HttpResponse:
    return render(
        request,
        "invoices/add_conversion_dialog.html",
        {"currencies": list(Currency), "invoice_id": pk},
    )


@login_required
@require_POST
def add_conversion(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    currency = Currency.from_code(request.POST["currency"])
    exchange_rate = Decimal(request.POST["exchange_rate"])
    invoice.add_conversion(exchange_rate, currency)
    repository.update(invoice)
    return render(
        request,
        "invoices/detail_conversions.html",
        {"invoice": invoice_viewmodel(invoice), "conversions": invoice.conversions()},
    )


@login_required
@require_POST
def edit_conversion_row(request: HttpRequest, pk: int) -> HttpResponse:
    currency = Currency.from_code(request.POST["currency"])
    exchange_rate = Decimal(request.POST["exchange_rate"] or 0)
    row = request.POST["row"]
    return render(
        request,
        "invoices/detail_conversion_row.html",
        {
            "edit": True,
            "row": row,
            "invoice_id": pk,
            "currency": currency,
            "exchange_rate": exchange_rate,
        },
    )


@login_required
@require_POST
def update_conversion(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    currency = Currency.from_code(request.POST["currency"])
    exchange_rate = Decimal(request.POST["exchange_rate"])
    invoice.add_conversion(exchange_rate, currency)
    repository.update(invoice)
    row = int(request.POST["row"])
    return render(
        request,
        "invoices/detail_conversion_row.html",
        {
            "row": row,
            "edit": False,
            "invoice_id": pk,
            "currency": currency,
            "exchange_rate": exchange_rate,
        },
    )


@login_required
@require_POST
def delete_conversion(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    currency = Currency.from_code(request.POST["currency"])
    invoice.remove_conversion(currency)
    repository.update(invoice)
    return HttpResponse()


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
        currency=invoice.currency(),
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
            related_funding_request = None
        case PublicationId(pub_id):
            publication = get_object_or_404(Publication, pk=pub_id)
            position_name = publication.title
            related_request = FundingRequest.objects.filter(publication_id=position.item).first()
            related_funding_request = None
            if related_request:
                related_funding_request = FundingRequestViewModel(
                    url=related_request.get_absolute_url(),
                    request_id=related_request.request_id,
                )
        case str(description):
            position_name = description
            related_funding_request = None

    return PositionViewModel(
        number=str(number),
        name=position_name,
        cost=position.cost,
        cost_type=position.cost_type.value,
        related_funding_request=related_funding_request,
        funding_source_id=position.funding_source,
    )


@login_required
@require_POST
def pay_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    invoice.pay()
    repository.update(invoice)
    response = (
        "<input disabled type='text' id='id-head-status' hx-swap-oob='true' value='"
        + str(invoice.status.name)
        + "' >"
    )
    response2 = "<small class='pill status-label approved'>" + str(invoice.status.name) + "</small>"
    full_response = response + response2
    return HttpResponse(full_response)


class FundingRequestViewModel(NamedTuple):
    url: str
    request_id: str


class PositionViewModel(NamedTuple):
    number: str
    name: str
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
    currency: Currency
    positions: list[PositionViewModel]
    tax: Money
    total: Money
