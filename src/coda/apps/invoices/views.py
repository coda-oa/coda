import datetime
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
from coda.invoice import (
    CostType,
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    ItemType,
    Position,
    Positions,
    TaxRate,
)
from coda.money import Currency, Money
from coda.publication import PublicationId

DEFAULT_TAX_RATE_PERCENTAGE = 19


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
    positions = assemble_positions(request)

    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    _tmp_invoice = temp_invoice(positions, currency)
    return render(
        request,
        "invoices/create.html",
        {
            "form": InvoiceForm(request.POST if request.POST else None),
            "currencies": list(Currency),
            "cost_types": [ct.value for ct in CostType],
            "publications": [search_result_for(pub) for pub in publications],
            "positions": positions,
            "tax": _tmp_invoice.tax().amount,
            "total": _tmp_invoice.total().amount,
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
        date=form.cleaned_data["date"],
        creditor=CreditorId(form.cleaned_data["creditor"].id),
        positions=parse_into_position_list(
            positions, Currency.from_code(form.cleaned_data["currency"])
        ),
        comment=form.cleaned_data["comment"],
    )


def temp_invoice(positions: list[dict[str, Any]], currency: Currency) -> Invoice:
    return Invoice.new(
        number="",
        date=datetime.date.today(),
        creditor=CreditorId(1),
        positions=parse_into_position_list(positions, currency),
        comment="",
    )


def parse_into_position_list(positions: list[dict[str, Any]], currency: Currency) -> Positions:
    return [
        Position(
            item=(
                PublicationId(int(position["id"])) if "id" in position else position["description"]
            ),
            cost=Money(position["cost_amount"], currency),
            cost_type=CostType(position["cost_type"]),
            tax_rate=TaxRate(int(position["tax_rate"]) / 100),
        )
        for position in positions
    ]


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
    if free_position := parse_added_free_position(request):
        positions.append(free_position)

    if new_publication_position := parse_added_publication_position(request):
        positions.append(new_publication_position)

    if remove_position := request.POST.get("remove-position"):
        positions.pop(int(remove_position) - 1)

    return positions


def parse_position_data(request: HttpRequest, index: int) -> dict[str, Any]:
    if request.POST.get(f"position-{index}-type") == "free":
        return parse_free_position(request, index)
    else:
        return parse_publication_position(request, index)


def parse_free_position(request: HttpRequest, index: int) -> dict[str, Any]:
    return {
        "type": "free",
        "description": request.POST.get(f"position-{index}-description", ""),
        "cost_amount": request.POST.get(f"position-{index}-cost", "0.00"),
        "cost_type": request.POST.get(f"position-{index}-cost-type", CostType.Other.value),
        "tax_rate": request.POST.get(f"position-{index}-taxrate", "0"),
    }


def parse_publication_position(request: HttpRequest, index: int) -> dict[str, Any]:
    return {
        "type": "publication",
        "id": request.POST.get(f"position-{index}-id", "0"),
        "title": request.POST.get(f"position-{index}-title", ""),
        "funding_request": {
            "request_id": request.POST.get(f"position-{index}-fundingrequest-id", ""),
            "url": request.POST.get(f"position-{index}-fundingrequest-url", ""),
        },
        "cost_amount": request.POST.get(f"position-{index}-cost", "0.00"),
        "cost_type": request.POST.get(f"position-{index}-cost-type", CostType.Other.value),
        "tax_rate": request.POST.get(f"position-{index}-taxrate", "0"),
        "description": "",
    }


def parse_added_publication_position(request: HttpRequest) -> dict[str, Any] | None:
    publication_id = request.POST.get("add-publication-position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return {
        "type": "publication",
        "id": str(publication.id),
        "title": publication.title,
        "funding_request": maybe_request_context(publication),
        "cost_amount": str(0.00),
        "cost_type": CostType.Publication_Charge.value,
        "tax_rate": str(DEFAULT_TAX_RATE_PERCENTAGE),
        "description": "",
    }


def parse_added_free_position(request: HttpRequest) -> dict[str, Any] | None:
    if request.POST.get("action") != "add-free-position":
        return None

    return {
        "type": "free",
        "description": request.POST.get("free-position-description", ""),
        "cost_amount": request.POST.get("free-position-cost", "0.00"),
        "cost_type": request.POST.get("free-position-cost-type", CostType.Other.value),
        "tax_rate": request.POST.get("free-position-taxrate", "0"),
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
