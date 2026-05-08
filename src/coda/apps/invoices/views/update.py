from dataclasses import asdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from coda import formdata
from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.create import build_position_errors, try_parse_invoice
from coda.apps.invoices.views.position_context import (
    DefaultContext as _DefaultContext,
)
from coda.apps.invoices.views.position_context import (
    funding_sources_context,
)
from coda.apps.invoices.views.position_views import safe_invoice_total
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.finance.dto.edit_position_dtos import PositionList
from coda.contexts.finance.services import invoice_parser, invoice_service
from coda.domain.finance.invoice import Invoice, InvoiceId
from coda.domain.money._currency import Currency
from coda.apps.invoices.models import Creditor

invoice_breadcrumb_title = generate_dynamic_title(
    model_name="Edit Invoice",
    fetch_fn=lambda pk: repository.get_by_id(InvoiceId(int(pk))),
    label_attr="number",
    fallback_attr="id",
    default_title="Edit Invoice",
)


@login_required
@breadcrumb(invoice_breadcrumb_title, parent_url_name="invoices:detail", preserve_filters=True)
def update_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))

    if request.method == "GET":
        positions = [invoice_parser.position_to_dto(p) for p in invoice.positions]
        position_list = PositionList(positions=positions)
        return render_edit_view(request, invoice, position_list)

    update_conversions(invoice, request.POST)

    position_list = formdata.map_to_model(PositionList, request.POST)
    parsed_invoice, errors = try_parse_invoice(
        request,
        position_list,
        conversions=invoice.conversions(),
    )

    if parsed_invoice:
        parsed_invoice.id = invoice.id
        invoice_service.save(parsed_invoice)
        return redirect("invoices:detail", pk=invoice.id)

    if errors:
        position_list = build_position_errors(errors, position_list)

    return render_edit_view(request, invoice, position_list)


@require_GET
@login_required
def free_position_cost_type_options(request: HttpRequest) -> HttpResponse:
    cost_type = request.GET.get("free-position-item-cost_type")

    if cost_type == "vat":
        return HttpResponse("")

    return render(request, "invoices/free_position_tax_rate.html")


def update_conversions(
    invoice: Invoice,
    post_data: dict[str, str],
) -> None:
    submitted_currencies: set[Currency] = set()

    for key in post_data:
        if key.startswith("exchange_rate_"):
            code = key.split("_")[-1]
            rate_str = post_data.get(key, "").strip()

            if not rate_str or not code:
                continue

            try:
                if (exchange_rate := Decimal(rate_str)) != 0:
                    currency = Currency.from_code(code)
                    invoice.add_conversion(exchange_rate, currency)
                    submitted_currencies.add(currency)
                else:
                    continue

            except (ValueError, ArithmeticError):
                continue

    existing_currencies = set(invoice.conversions().keys())
    to_remove = existing_currencies - submitted_currencies

    for currency in to_remove:
        invoice.remove_conversion(currency)


def render_edit_view(
    request: HttpRequest,
    invoice: Invoice,
    position_list: PositionList,
) -> HttpResponse:
    home_currency = GlobalPreferences.get_home_currency()
    conversion_currency = None
    exchange_rate = Decimal(0)
    if invoice.conversions():
        conversion_currency, exchange_rate = next(iter(invoice.conversions().items()))
        exchange_rate = invoice.conversions().get(home_currency, Decimal("0"))

    return render(
        request,
        "invoices/create.html",
        _DefaultContext
        | funding_sources_context(position_list.positions)
        | asdict(safe_invoice_total(position_list.positions, invoice.currency()))
        | {
            "mode_name": "Edit",
            "form": _restore_form(request, invoice),
            "invoice_id": invoice.id,
            "conversions": invoice.conversions(),
            "invoice_currency": invoice.currency().code,
            "home_currency": home_currency.code,
            "conversion_currency": conversion_currency.code if conversion_currency else None,
            "exchange_rate": exchange_rate,
            "selected_currency": invoice.currency().code,
            "position_list": position_list,
            "creditors": Creditor.objects.all().order_by("name"),
        },
    )


def _restore_form(request: HttpRequest, invoice: Invoice) -> InvoiceForm:
    if request.method == "POST":
        return InvoiceForm(request.POST)
    return InvoiceForm.from_invoice(invoice)
