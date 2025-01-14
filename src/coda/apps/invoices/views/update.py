from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from coda.apps.invoices import repository
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.views.create import _DefaultContext, save_invoice
from coda.apps.invoices.views.position_list import (
    ErrorDict,
    existing_positions,
    invoice_total_context,
)
from coda.apps.invoices.views.positions import to_position_dto
from coda.invoice import InvoiceId


@login_required
def update_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    if request.method == "POST":
        invoice_id, errors = save_invoice(request, invoice_id=invoice.id)
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
            }
        )

    return render(
        request,
        "invoices/create.html",
        _DefaultContext
        | invoice_total_context(positions, invoice.currency().code)
        | errors
        | {"mode_name": "Edit", "form": form, "positions": positions},
    )
