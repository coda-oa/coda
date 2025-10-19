from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.position_list import (
    ErrorDict,
    _DefaultContext,
    existing_positions,
    parse_position_dtos,
)
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.finance.services import invoice_service
from coda.domain.invoice import InvoiceId
from coda.domain.money import Currency


@login_required
@breadcrumb("Create Invoice", parent_url_name="invoices:list", preserve_filters=True)
def create_invoice(request: HttpRequest) -> HttpResponse:
    home_currency = GlobalPreferences.get_home_currency()
    errors = ErrorDict(errors={})

    conversion = {}
    currency_code = request.POST.get(f"conversion_currency_{home_currency.code}", "").strip()
    exchange_rate_str = request.POST.get(f"exchange_rate_{home_currency.code}", "").strip()

    if currency_code and exchange_rate_str:
        home_currency = Currency.from_code(currency_code)
        exchange_rate = Decimal(exchange_rate_str)
        conversion = {home_currency: exchange_rate}

    if request.POST.get("action") == "create":
        new_id, errors = save_invoice(request, conversions=conversion)
        if new_id:
            return redirect("invoices:detail", pk=new_id)

    return render(
        request,
        "invoices/create.html",
        {
            "mode_name": "Create",
            "form": InvoiceForm(request.POST if request.POST else None),
            "positions": existing_positions(request),
            "home_currency_ceate": home_currency.code,
        }
        | _DefaultContext
        | errors,
    )


def save_invoice(
    request: HttpRequest,
    *,
    invoice_id: InvoiceId | None = None,
    conversions: dict[Currency, Decimal],
) -> tuple[InvoiceId | None, ErrorDict]:
    form = InvoiceForm(request.POST)
    if not form.is_valid():
        return None, ErrorDict(errors={})

    number_of_positions = int(request.POST.get("number-of-positions", 0))
    _positions = [parse_position_dtos(request, i) for i in range(1, number_of_positions + 1)]
    positions = [p for p in _positions if p is not None]

    try:
        invoice = invoice_service.parse_invoice(form.invoice_head(), positions)
        invoice.id = invoice_id
        for currency, rate in conversions.items():
            invoice.add_conversion(rate, currency)

        return invoice_service.save(invoice), ErrorDict(errors={})
    except invoice_service.InvoiceParseError as e:
        return None, ErrorDict(
            errors={
                f"position-{i}-error": err.message()
                for i, p in enumerate(positions, start=1)
                if (err := e.error_for(p)) is not None
            }
        )
