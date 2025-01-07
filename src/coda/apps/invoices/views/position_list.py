import datetime
from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypedDict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.invoices.views.positions import (
    CommonPosition,
    ContractPosition,
    FreePosition,
    PublicationPosition,
    RelatedFundingRequest,
    get_position_type,
)
from coda.apps.publications.models import Publication
from coda.contract import ContractId
from coda.invoice import CostType, CreditorId, Invoice, ItemType, Position, Positions, TaxRate
from coda.money import Currency, Money

_CostTypes = [ct.value for ct in CostType]


class ErrorDict(TypedDict):
    errors: dict[str, str]


@login_required
def switch_position_tab(request: HttpRequest) -> HttpResponse:
    tab = request.GET["tab"]
    return render(request, "invoices/add_positions.html", {"tab": tab, "cost_types": _CostTypes})


@login_required
def add_position(request: HttpRequest) -> HttpResponse:
    positions = existing_positions(request) + added_positions(request)
    return render_positions(request, positions)


@login_required
def remove_position(request: HttpRequest) -> HttpResponse:
    positions = existing_positions(request)
    if remove_position := request.POST.get("remove-position"):
        positions.pop(int(remove_position) - 1)

    return render_positions(request, positions)


@login_required
def invoice_total(request: HttpRequest) -> HttpResponse:
    positions = existing_positions(request)
    return render_positions(request, positions)


def temp_invoice(positions: list[CommonPosition[ItemType]], currency: Currency) -> Invoice:
    return Invoice.new(
        number="",
        date=datetime.date.today(),
        creditor=CreditorId(1),
        positions=parse_into_position_list(positions, currency, lambda p: p.parse_safe()),
        comment="",
    )


def parse_into_position_list(
    positions: list[CommonPosition[ItemType]],
    currency: Currency,
    item_parser: Callable[[CommonPosition[ItemType]], ItemType],
) -> Positions:
    return [
        parse_position(index, position, currency, item_parser)
        for index, position in enumerate(positions, start=1)
    ]


def parse_position(
    index: int,
    position: CommonPosition[ItemType],
    currency: Currency,
    item_parser: Callable[[CommonPosition[ItemType]], ItemType],
) -> Position[ItemType]:
    try:
        return Position(
            item=item_parser(position),
            cost=Money(position.cost_amount, currency),
            cost_type=CostType(position.cost_type),
            tax_rate=TaxRate.from_percentage(position.tax_rate),
        )
    except Exception as e:
        raise PositionError(index, e)


def added_positions(request: HttpRequest) -> list[CommonPosition[ItemType]]:
    _positions = [parser(request) for parser in _ADD_POSITION_PARSERS.values()]
    return [p for p in _positions if p is not None]


def existing_positions(request: HttpRequest) -> list[CommonPosition[ItemType]]:
    number_of_positions = int(request.POST.get("number-of-positions", 0))
    _positions = [parse_position_data(request, i) for i in range(1, number_of_positions + 1)]
    positions = [p for p in _positions if p is not None]
    return positions


def parse_position_data(request: HttpRequest, index: int) -> CommonPosition[ItemType] | None:
    position_type_str = request.POST.get(f"position-{index}-type")
    if not position_type_str:
        return None

    position_type = get_position_type(position_type_str)
    return position_type.from_request(request.POST, f"position-{index}-")


def parse_added_publication_position(request: HttpRequest) -> PublicationPosition | None:
    publication_id = request.POST.get("add-publication-position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return PublicationPosition(
        id=publication.id,
        title=publication.title,
        funding_request=maybe_request_context(publication),
    )


def maybe_request_context(publication: Publication) -> RelatedFundingRequest:
    if hasattr(publication, "fundingrequest"):
        return RelatedFundingRequest(
            request_id=publication.fundingrequest.request_id,
            url=publication.fundingrequest.get_absolute_url(),
        )
    else:
        return RelatedFundingRequest(request_id=None)


def parse_added_contract_position(request: HttpRequest) -> ContractPosition | None:
    if request.POST.get("action") != "add-contract-position":
        return None

    contract_id = ContractId(request.POST.get("contract-id", ""))
    year = int(request.POST.get("contract-year", ""))
    contract_name = request.POST.get("contract-name", "")

    return ContractPosition(id=contract_id, name=contract_name, contract_year=year)


def parse_added_free_position(request: HttpRequest) -> FreePosition | None:
    if request.POST.get("action") != "add-free-position":
        return None

    return FreePosition(
        cost_amount=request.POST.get("free-position-cost-amount", Decimal("0.00")),
        cost_type=request.POST.get("free-position-cost-type", CostType.Other.value),
        tax_rate=Decimal(request.POST.get("free-position-tax-rate", "0")),
        description=request.POST.get("free-position-description", ""),
    )


def render_positions(
    request: HttpRequest, positions: list[CommonPosition[ItemType]]
) -> HttpResponse:
    return render(
        request,
        "invoices/invoice_positions.html",
        {"positions": positions, "cost_types": _CostTypes}
        | invoice_total_context(positions, request.POST.get("currency", "EUR")),
    )


def invoice_total_context(
    positions: list[CommonPosition[ItemType]], currency: str
) -> dict[str, Any]:
    _currency = Currency.from_code(currency)
    _tmp_invoice = temp_invoice(positions, _currency)
    return {
        "tax": _tmp_invoice.tax().amount,
        "total": _tmp_invoice.total().amount,
    }


_ADD_POSITION_PARSERS = {
    "publication": parse_added_publication_position,
    "contract": parse_added_contract_position,
    "free": parse_added_free_position,
}


class PositionError(Exception):
    def __init__(self, position: int, inner: Exception, *args: Any) -> None:
        super().__init__(*args)
        self.position = position
        self.inner = inner

    def message(self) -> str:
        return str(self.inner)
