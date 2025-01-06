from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.invoices import services
from coda.apps.invoices.views.positions import to_position_dto
from coda.invoice import InvoiceId


@login_required
def update_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = services.get_by_id(InvoiceId(pk))
    positions = [to_position_dto(p) for p in invoice.positions]
    return render(request, "invoices/create.html", {"positions": positions})
