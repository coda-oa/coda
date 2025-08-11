from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.create import save_invoice
from coda.apps.invoices.views.position_list import (
    _DefaultContext,
    ErrorDict,
    existing_positions,
    funding_sources_context,
    invoice_total_context,
)
from coda.apps.invoices.views.positions import to_position_dto
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.invoice import InvoiceId
from coda.domain.money._currency import Currency
from decimal import Decimal


@login_required
def update_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))

    home_currency = GlobalPreferences.get_home_currency()

    conversions = invoice.conversions()
    conversion_currency = None
    exchange_rate = None
    if conversions:
        conversion_currency, exchange_rate = next(iter(conversions.items()))

    selected_currency = request.POST.get("currency")
    currency_code = request.POST.get("conversion_currency", "").strip()
    exchange_rate_str = request.POST.get("exchange_rate", "").strip()

    if request.method == "POST":
        if currency_code and exchange_rate_str:
            conversion_currency = Currency.from_code(request.POST["conversion_currency"])
            exchange_rate = Decimal(request.POST["exchange_rate"])
            invoice.add_conversion(exchange_rate, conversion_currency)
            repository.update(invoice)

        if selected_currency == home_currency.code or not exchange_rate_str:
            for currency in list(invoice.conversions().keys()):
                invoice.remove_conversion(currency)
            repository.update(invoice)

        invoice_id, errors = save_invoice(request, invoice_id=invoice.id, existing_invoice=invoice)
        if invoice_id:
            return redirect("invoices:detail", pk=invoice_id)

        form = InvoiceForm(request.POST)
        positions = existing_positions(request)
    else:
        positions = [to_position_dto(p) for p in invoice.positions]
        errors = ErrorDict(errors={})
        form = InvoiceForm(
            {
                "number": invoice.number,
                "creditor": invoice.creditor,
                "date": invoice.date,
                "status": invoice.status.value,
                "comment": invoice.comment,
                "currency": invoice.currency().code,
                "external_invoice_id": invoice.external_invoice_id,
            }
        )

    return render(
        request,
        "invoices/create.html",
        _DefaultContext
        | funding_sources_context()
        | invoice_total_context(positions, invoice.currency().code)
        | errors
        | {
            "mode_name": "Edit",
            "form": form,
            "positions": positions,
            "invoice_id": invoice.id,
            "conversions": invoice.conversions(),
            "invoice_currency": invoice.currency().code,
            "home_currency": home_currency.code,
            "conversion_currency": conversion_currency.code if conversion_currency else None,
            "exchange_rate": exchange_rate if exchange_rate is not None else "",
            "selected_currency": selected_currency,
        },
    )
