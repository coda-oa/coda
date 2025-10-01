from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda.apps.invoices import services
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.position_list import (
    ErrorDict,
    PositionError,
    _DefaultContext,
    existing_positions,
    parse_into_position_list,
    parse_position_data,
)
from coda.apps.invoices.views.position_dtos.edit_position_dtos import AnyPositionDto
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.invoice import CreditorId, Invoice, InvoiceId, PaymentStatus

from coda.domain.money._currency import Currency
from decimal import Decimal
from coda.apps.breadcrumbs.decorators import breadcrumb


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

    try:
        number_of_positions = int(request.POST.get("number-of-positions", 0))
        _positions = [parse_position_data(request, i) for i in range(1, number_of_positions + 1)]
        positions = [p for p in _positions if p is not None]
        return (
            services.save(
                parse_invoice(
                    form,
                    positions,
                    invoice_id=invoice_id,
                    conversions=conversions,
                )
            ),
            ErrorDict(errors={}),
        )
    except PositionError as e:
        return None, ErrorDict(errors={f"position-{e.position}-error": e.message()})


def parse_invoice(
    form: InvoiceForm,
    positions: list[AnyPositionDto],
    conversions: dict[Currency, Decimal],
    invoice_id: InvoiceId | None = None,
) -> Invoice:
    invoice = Invoice(
        id=invoice_id,
        number=form.cleaned_data["number"],
        date=form.cleaned_data["date"],
        status=PaymentStatus(form.cleaned_data["status"]),
        creditor=CreditorId(form.cleaned_data["creditor"].id),
        positions=parse_into_position_list(positions, form.get_currency(), parse_safe=False),
        comment=form.cleaned_data["comment"],
        external_invoice_id=form.cleaned_data["external_invoice_id"],
    )

    for currency, rate in conversions.items():
        invoice.add_conversion(rate, currency)

    return invoice
