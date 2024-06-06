import datetime
from typing import NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.services import as_domain_object
from coda.apps.publications.models import Publication
from coda.invoice import FundingSourceId, ItemType, Position
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
    creditor_name = invoice_model.creditor.name
    invoice = as_domain_object(invoice_model)
    return InvoiceViewModel(
        url=invoice_model.get_absolute_url(),
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        creditor_name=creditor_name,
        positions=[
            position_viewmodel(position, i) for i, position in enumerate(invoice.positions, start=1)
        ],
        total=invoice.total(),
    )


def position_viewmodel(position: Position[ItemType], number: int) -> "PositionViewModel":
    match position.item:
        case int(pub_id):
            publication = get_object_or_404(Publication, pk=pub_id)
            publication_title = publication.title
            submitter = cast(Author, publication.submitting_author).name
            related_request = FundingRequest.objects.filter(publication_id=position.item).first()
            related_funding_request = None
            if related_request:
                related_funding_request = FundingRequestViewModel(
                    url=related_request.get_absolute_url(),
                    request_id=related_request.request_id,
                )
        case str(description):
            publication_title = description
            submitter = ""
            related_funding_request = None

    return PositionViewModel(
        number=str(number),
        publication_name=publication_title,
        publication_submitter=submitter,
        cost=position.cost,
        cost_type=position.cost_type.value,
        related_funding_request=related_funding_request,
        funding_source_id=position.funding_source,
    )


class FundingRequestViewModel(NamedTuple):
    url: str
    request_id: str


class PositionViewModel(NamedTuple):
    number: str
    publication_name: str
    publication_submitter: str
    cost: Money
    cost_type: str
    related_funding_request: FundingRequestViewModel | None
    funding_source_id: FundingSourceId | None


class InvoiceViewModel(NamedTuple):
    url: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    positions: list[PositionViewModel]
    total: Money
