import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from coda.apps.invoices import repository, services
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.views.position_list import _DefaultContext
from coda.apps.invoices.views.position_list import funding_sources_context
from coda.apps.invoices.views.positions import AnyPositionDto, to_position_dto
from coda.apps.views import EntityListView
from coda.domain.date import DateRange
from coda.domain.invoice import Invoice, InvoiceId, PaymentStatus
from coda.domain.money import Money
from coda.domain.money._currency import Currency


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
    editable = False
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
            "editable": editable,
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
        positions=[to_position_dto(position) for position in invoice.positions],
        tax=invoice.tax(),
        total=invoice.total(),
        net=invoice.net(),
        comment=invoice.comment,
        external_invoice_id=invoice.external_invoice_id,
    )


@login_required
@require_POST
def pay_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    if request.POST.get("action") == "pay":
        invoice.pay()
    elif request.POST.get("action") == "reset_payment":
        invoice.reset_payment()
    services.save(invoice)
    return redirect("invoices:detail", pk=invoice.id)


class InvoiceViewModel(NamedTuple):
    id: int
    url: str
    status: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    currency: Currency
    positions: list[AnyPositionDto]
    tax: Money
    total: Money
    net: Money
    comment: str
    external_invoice_id: str
