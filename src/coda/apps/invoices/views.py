from typing import NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.services import as_domain_object
from coda.apps.publications.models import Publication
from coda.fundingrequest import FundingRequestId
from coda.invoice import FundingSourceId, Position
from coda.money import Money


@login_required
def invoice_list(request: HttpRequest) -> HttpResponse:
    invoices = map(invoice_viewmodel, InvoiceModel.objects.all())
    return render(request, "invoices/list.html", {"invoices": invoices})


@login_required
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice_model = get_object_or_404(InvoiceModel, pk=pk)
    return render(request, "invoices/detail.html", {"invoice": invoice_viewmodel(invoice_model)})


def invoice_viewmodel(invoice_model: InvoiceModel) -> "InvoiceViewModel":
    recipient_name = invoice_model.recipient.name
    invoice = as_domain_object(invoice_model)
    return InvoiceViewModel(
        url=invoice_model.get_absolute_url(),
        number=invoice.number,
        recipient=invoice.recipient,
        recipient_name=recipient_name,
        positions=[position_viewmodel(position) for position in invoice.positions],
    )


def position_viewmodel(position: Position) -> "PositionViewModel":
    publication = get_object_or_404(Publication, pk=position.publication)
    related_request = FundingRequest.objects.filter(publication_id=position.publication).first()
    if related_request:
        related_funding_request = FundingRequestViewModel(
            url=related_request.get_absolute_url(),
            request_id=FundingRequestId(related_request.id),
        )
    else:
        related_funding_request = None

    return PositionViewModel(
        number=str(position.number),
        publication_name=publication.title,
        publication_submitter=cast(Author, publication.submitting_author).name,
        cost=position.cost,
        description=position.description,
        related_funding_request=related_funding_request,
        funding_source_id=position.funding_source,
    )


class FundingRequestViewModel(NamedTuple):
    url: str
    request_id: FundingRequestId


class PositionViewModel(NamedTuple):
    number: str
    publication_name: str
    publication_submitter: str
    cost: Money
    description: str
    related_funding_request: FundingRequestViewModel | None
    funding_source_id: FundingSourceId | None


class InvoiceViewModel(NamedTuple):
    url: str
    number: str
    recipient: int
    recipient_name: str
    positions: list[PositionViewModel]
