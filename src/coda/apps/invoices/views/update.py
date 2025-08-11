from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.create import save_invoice
from coda.apps.invoices.views.position_list import (
    ErrorDict,
    _DefaultContext,
    existing_positions,
    funding_sources_context,
    invoice_total_context,
)
from coda.apps.invoices.views.positions import AnyPositionDto, to_position_dto
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.invoice import Invoice, InvoiceId
from coda.domain.money._currency import Currency


@login_required
def update_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))

    if request.method == "GET":
        positions = [to_position_dto(p) for p in invoice.positions]
        return render_edit_view(request, invoice, positions)

    conversion_currency_code = request.POST.get("conversion_currency", "").strip()
    exchange_rate_str = request.POST.get("exchange_rate", "").strip()
    update_conversions(invoice, conversion_currency_code, exchange_rate_str)

    invoice_id, errors = save_invoice(
        request,
        invoice_id=invoice.id,
        conversions=invoice.conversions(),
    )

    if invoice_id:
        return redirect("invoices:detail", pk=invoice_id)

    return render_edit_view(request, invoice, existing_positions(request), errors=errors)


def update_conversions(
    invoice: Invoice, conversion_currency_code: str, exchange_rate_str: str
) -> None:
    if not (conversion_currency_code and exchange_rate_str):
        invoice.clear_conversions()
        return

    conversion_currency = Currency.from_code(conversion_currency_code)
    exchange_rate = Decimal(exchange_rate_str)
    invoice.add_conversion(exchange_rate, conversion_currency)


def render_edit_view(
    request: HttpRequest,
    invoice: Invoice,
    positions: list[AnyPositionDto],
    errors: ErrorDict | None = None,
) -> HttpResponse:
    home_currency = GlobalPreferences.get_home_currency()
    errors = errors or ErrorDict(errors={})
    conversion_currency = None
    exchange_rate = Decimal(0)
    if invoice.conversions():
        conversion_currency, exchange_rate = next(iter(invoice.conversions().items()))

    return render(
        request,
        "invoices/create.html",
        _DefaultContext
        | funding_sources_context()
        | invoice_total_context(positions, invoice.currency().code)
        | errors
        | {
            "mode_name": "Edit",
            "form": _restore_form(request, invoice),
            "positions": positions,
            "invoice_id": invoice.id,
            "conversions": invoice.conversions(),
            "invoice_currency": invoice.currency().code,
            "home_currency": home_currency.code,
            "conversion_currency": conversion_currency.code if conversion_currency else None,
            "exchange_rate": exchange_rate,
        },
    )


def _restore_form(request: HttpRequest, invoice: Invoice) -> InvoiceForm:
    if request.method == "POST":
        return InvoiceForm(request.POST)
    return InvoiceForm.from_invoice(invoice)
