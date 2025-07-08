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
from coda.apps.invoices.views.positions import AnyPositionDto
from coda.domain.invoice import CreditorId, Invoice, InvoiceId, PaymentStatus


@login_required
def create_invoice(request: HttpRequest) -> HttpResponse:
    errors = ErrorDict(errors={})
    if request.POST.get("action") == "create":
        new_id, errors = save_invoice(request)
        if new_id:
            return redirect("invoices:detail", pk=new_id)

    return render(
        request,
        "invoices/create.html",
        {
            "mode_name": "Create",
            "form": InvoiceForm(request.POST if request.POST else None),
            "positions": existing_positions(request),
        }
        | _DefaultContext
        | errors,
    )


def save_invoice(
    request: HttpRequest, *, invoice_id: InvoiceId | None = None
) -> tuple[InvoiceId | None, ErrorDict]:
    form = InvoiceForm(request.POST)
    if not form.is_valid():
        return None, ErrorDict(errors={})

    try:
        number_of_positions = int(request.POST.get("number-of-positions", 0))
        _positions = [parse_position_data(request, i) for i in range(1, number_of_positions + 1)]
        positions = [p for p in _positions if p is not None]
        return (
            services.save(parse_invoice(form, positions, invoice_id=invoice_id)),
            ErrorDict(errors={}),
        )
    except PositionError as e:
        return None, ErrorDict(errors={f"position-{e.position}-error": e.message()})


def parse_invoice(
    form: InvoiceForm,
    positions: list[AnyPositionDto],
    invoice_id: InvoiceId | None = None,
) -> Invoice:
    return Invoice(
        id=invoice_id,
        number=form.cleaned_data["number"],
        date=form.cleaned_data["date"],
        status=PaymentStatus(form.cleaned_data["status"]),
        creditor=CreditorId(form.cleaned_data["creditor"].id),
        positions=parse_into_position_list(positions, form.get_currency(), parse_safe=False),
        comment=form.cleaned_data["comment"],
        external_invoice_id=form.cleaned_data["external_invoice_id"],
    )
