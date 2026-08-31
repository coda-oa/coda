from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda import formdata
from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.invoices.forms import InvoiceForm, CreditorForm
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.views.position_context import DefaultContext, funding_sources_context
from coda.apps.invoices.views.position_parsers import PositionDtoWithErrors
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.finance.dto.edit_position_dtos import PositionList
from coda.contexts.finance.services.invoice_import import (
    InvoiceParseError,
    parse_invoice,
    save,
)
from coda.domain.finance.invoice import Invoice, InvoiceId, UnassignedCosts
from coda.domain.money import Currency
from django.views.decorators.http import require_GET, require_POST


@login_required
@breadcrumb("Create Invoice", parent_url_name="invoices:list", preserve_filters=True)
def create_invoice(request: HttpRequest) -> HttpResponse:
    home_currency = GlobalPreferences.get_home_currency()

    conversion = {}
    currency_code = request.POST.get(f"conversion_currency_{home_currency.code}", "").strip()
    exchange_rate_str = request.POST.get(f"exchange_rate_{home_currency.code}", "").strip()

    if currency_code and exchange_rate_str:
        home_currency = Currency.from_code(currency_code)
        exchange_rate = Decimal(exchange_rate_str)
        conversion = {home_currency: exchange_rate}

    position_list = formdata.map_to_model(PositionList, request.POST)
    if request.POST.get("action") == "create":
        invoice, errors = try_parse_invoice(request, position_list, conversions=conversion)
        if invoice:
            new_id = save(invoice)
            return redirect("invoices:detail", pk=new_id)

        if errors:
            position_list = build_position_errors(errors, position_list)

    return render(
        request,
        "invoices/create.html",
        {
            "mode_name": "Create",
            "form": InvoiceForm(request.POST if request.POST else None),
            "home_currency_ceate": home_currency.code,
            "position_list": position_list,
            "creditors": Creditor.objects.all().order_by("name"),
        }
        | DefaultContext
        | funding_sources_context(),
    )


def try_parse_invoice(
    request: HttpRequest,
    position_list: PositionList,
    *,
    conversions: dict[Currency, Decimal],
    ) -> tuple[Invoice | None, InvoiceParseError | None]:
    form = InvoiceForm(request.POST)
    if not form.is_valid():
        return None, None

    try:
        invoice = parse_invoice(form.invoice_head(), position_list.positions)
        for currency, rate in conversions.items():
            invoice.add_conversion(rate, currency)

        return invoice, None
    except UnassignedCosts:
        messages.error(request, "Invoice has unassigned costs")
        return None, None
    except InvoiceParseError as e:
        return None, e


def build_position_errors(
    errors: InvoiceParseError, position_list: PositionList
) -> PositionList:
    error_positions = PositionList(positions=[])

    for dto in position_list.positions:
        err = errors.error_for(dto)
        if err:
            error_positions.positions.append(PositionDtoWithErrors.from_dto(dto, err.message()))
        else:
            error_positions.positions.append(dto)

    return error_positions


@login_required
@require_GET
def creditor_create_modal(request: HttpRequest) -> HttpResponse:
    form = CreditorForm()
    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": "Creditor",
            "form": form,
            "entity_create_url": "invoices:creditor_create_modal_submit",
        },
    )


@login_required
@require_POST
def creditor_create_modal_submit(request: HttpRequest) -> HttpResponse:
    form = CreditorForm(request.POST)

    if form.is_valid():
        creditor = form.save()

        creditors = Creditor.objects.all().order_by("name")

        return render(
            request,
            "invoices/partials/creditor_create_success.html",
            {
                "creditors": creditors,
                "selected_creditor_id": creditor.id,
                "required": True,
            },
        )
    else:
        return render(
            request,
            "partials/entity_creation_modal.html",
            {
                "entity_name": "Creditor",
                "form": form,
                "entity_create_url": "invoices:creditor_create_modal_submit",
            },
        )
