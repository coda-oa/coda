from collections.abc import Iterable
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from coda.apps.authors.models import Author
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.forms import InvoiceForm
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.services import as_domain_object, invoice_create
from coda.apps.publications.models import Publication
from coda.invoice import FundingSourceId, Invoice, InvoiceId, Position, PositionNumber, PublisherId
from coda.money import Currency, Money
from coda.publication import PublicationId


@login_required
def invoice_list(request: HttpRequest) -> HttpResponse:
    invoices = map(invoice_viewmodel, InvoiceModel.objects.all())
    return render(request, "invoices/list.html", {"invoices": invoices})


@login_required
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice_model = get_object_or_404(InvoiceModel, pk=pk)
    return render(request, "invoices/detail.html", {"invoice": invoice_viewmodel(invoice_model)})


@login_required
def create_invoice(request: HttpRequest) -> HttpResponse:
    if request.POST.get("action") == "create":
        new_id = save_invoice(request)
        if new_id:
            return redirect("invoices:detail", pk=new_id)

    publications = search_publications(request)
    return render(
        request,
        "invoices/create.html",
        {
            "form": InvoiceForm(request.POST if request.POST else None),
            "currencies": list(Currency),
            "publications": [search_result_for(pub) for pub in publications],
            "positions": assemble_positions(request),
        },
    )


def save_invoice(request: HttpRequest) -> InvoiceId | None:
    form = InvoiceForm(request.POST)
    if form.is_valid():
        number_of_positions = int(request.POST.get("number-of-positions", 0))
        positions = [parse_position_data(request, i) for i in range(1, number_of_positions + 1)]
        return invoice_create(parse_invoice(form, positions))

    return None


def parse_invoice(form: InvoiceForm, positions: list[dict[str, Any]]) -> Invoice:
    return Invoice.new(
        number=form.cleaned_data["number"],
        recipient=PublisherId(form.cleaned_data["creditor"].id),
        positions=[
            Position(
                number=PositionNumber(position["number"]),
                publication=PublicationId(position["id"]),
                cost=Money(position["cost_amount"], Currency[position["cost_currency"]]),
            )
            for position in positions
        ],
    )


def search_publications(request: HttpRequest) -> Iterable[Publication]:
    query = request.POST.get("q", "")
    creditor = request.POST.get("creditor", "")
    if query:
        complete_query = Q(title__icontains=query)
        if creditor:
            complete_query &= Q(journal__publisher_id=creditor)

        return Publication.objects.filter(complete_query)
    else:
        return Publication.objects.none()


def assemble_positions(request: HttpRequest) -> list[dict[str, Any]]:
    number_of_positions = int(request.POST.get("number-of-positions", 0))
    positions = [parse_position_data(request, i) for i in range(1, number_of_positions + 1)]
    new_position = added_position(request, len(positions) + 1)
    if new_position:
        positions.append(new_position)

    return positions


def parse_position_data(request: HttpRequest, index: int) -> dict[str, Any]:
    return {
        "number": request.POST.get(f"position-{index}-number", "0"),
        "id": int(request.POST.get(f"position-{index}-id", 0)),
        "title": request.POST.get(f"position-{index}-title", ""),
        "funding_request": {
            "request_id": request.POST.get(f"position-{index}-fundingrequest-id", ""),
            "url": request.POST.get(f"position-{index}-fundingrequest-url", ""),
        },
        "cost_amount": float(request.POST.get(f"position-{index}-cost", 0.00)),
        "cost_currency": request.POST.get(f"position-{index}-currency", "EUR"),
        "description": "",
    }


def added_position(request: HttpRequest, number: int) -> dict[str, Any] | None:
    publication_id = request.POST.get("add_position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return {
        "id": publication.id,
        "number": str(number),
        "title": publication.title,
        "funding_request": maybe_request_context(publication),
        "cost_amount": 0.00,
        "cost_currency": "EUR",
        "description": "",
    }


def search_result_for(publication: Publication) -> dict[str, Any]:
    return {
        "id": publication.id,
        "title": publication.title,
        "funding_request": maybe_request_context(publication),
    }


def maybe_request_context(publication: Publication) -> dict[str, Any]:
    if hasattr(publication, "fundingrequest"):
        return {
            "request_id": publication.fundingrequest.request_id,
            "url": publication.fundingrequest.get_absolute_url(),
        }
    else:
        return {"request_id": "", "url": ""}


def invoice_viewmodel(invoice_model: InvoiceModel) -> "InvoiceViewModel":
    recipient_name = invoice_model.recipient.name
    invoice = as_domain_object(invoice_model)
    return InvoiceViewModel(
        url=invoice_model.get_absolute_url(),
        number=invoice.number,
        recipient=invoice.recipient,
        recipient_name=recipient_name,
        positions=[position_viewmodel(position) for position in invoice.positions],
        total=invoice.total(),
    )


def position_viewmodel(position: Position) -> "PositionViewModel":
    publication = get_object_or_404(Publication, pk=position.publication)
    related_request = FundingRequest.objects.filter(publication_id=position.publication).first()
    if related_request:
        related_funding_request = FundingRequestViewModel(
            url=related_request.get_absolute_url(),
            request_id=related_request.request_id,
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
    request_id: str


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
    total: Money
