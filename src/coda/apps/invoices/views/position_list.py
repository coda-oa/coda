from dataclasses import asdict
from typing import Any, TypedDict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.fundingrequests import repository
from coda.apps.invoices.models import FundingSource
from coda.contexts.finance.dto.edit_position_dtos import (
    AnyPositionDto,
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
    RelatedFundingRequest,
)
from coda.apps.publications.models import Publication
from coda.contexts.finance.services import invoice_parser
from coda.domain.invoice import ContractCostType, PublicationCostType
from coda.domain.money import Currency
from coda.domain.publication.publication import PublicationId

_PublicationCostTypes = [ct.value for ct in PublicationCostType]
_ContractCostTypes = [ct.value for ct in ContractCostType]


class ErrorDict(TypedDict):
    errors: dict[str, str]


@login_required
def switch_position_tab(request: HttpRequest) -> HttpResponse:
    tab = request.GET["tab"]
    return render(
        request,
        "invoices/add_positions.html",
        {
            "tab": tab,
            "publication_cost_types": _PublicationCostTypes,
            "contract_cost_types": _ContractCostTypes,
        },
    )


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
    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    return render(
        request,
        "invoices/position_summary.html",
        asdict(invoice_parser.invoice_total(positions, currency)),
    )


def added_positions(request: HttpRequest) -> list[AnyPositionDto]:
    _positions = [parser(request) for parser in _ADD_POSITION_PARSERS.values()]
    return [p for p in _positions if p is not None]


def existing_positions(request: HttpRequest) -> list[AnyPositionDto]:
    number_of_positions = int(request.POST.get("number-of-positions", 0))
    _positions = [parse_position_dtos(request, i) for i in range(1, number_of_positions + 1)]
    positions = [p for p in _positions if p is not None]
    return positions


def parse_position_dtos(request: HttpRequest, index: int) -> AnyPositionDto | None:
    position_type_str = request.POST.get(f"position-{index}-type")
    if not position_type_str:
        return None

    position_type = invoice_parser.get_position_type(position_type_str)
    return position_type.from_request(request.POST, f"position-{index}-")


def parse_added_publication_position(request: HttpRequest) -> PublicationPositionDto | None:
    publication_id = request.POST.get("add-publication-position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return PublicationPositionDto(
        id=publication.pk,
        title=publication.title,
        funding_request=maybe_request_context(publication),
    )


def maybe_request_context(publication: Publication) -> RelatedFundingRequest:
    reference = repository.find_reference_by_publication(PublicationId(publication.pk))
    if reference:
        return RelatedFundingRequest(request_id=reference.request_id, url=reference.url)

    return RelatedFundingRequest()


def parse_added_contract_position(request: HttpRequest) -> ContractPositionDto | None:
    if request.POST.get("action") != "add-contract-position":
        return None

    return ContractPositionDto.from_request(request.POST, prefix="contract-")


def parse_added_free_position(request: HttpRequest) -> FreePositionDto | None:
    if request.POST.get("action") != "add-free-position":
        return None

    return FreePositionDto.from_request(request.POST, prefix="free-position-")


def render_positions(request: HttpRequest, positions: list[AnyPositionDto]) -> HttpResponse:
    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    return render(
        request,
        "invoices/invoice_positions.html",
        {"positions": positions}
        | _DefaultContext
        | funding_sources_context()
        | asdict(invoice_parser.invoice_total(positions, currency)),
    )


def funding_sources_context() -> dict[str, Any]:
    return {"funding_sources": FundingSource.objects.all()}


_ADD_POSITION_PARSERS = {
    "publication": parse_added_publication_position,
    "contract": parse_added_contract_position,
    "free": parse_added_free_position,
}


_DefaultContext = {
    "publication_cost_types": _PublicationCostTypes,
    "contract_cost_types": _ContractCostTypes,
    "currencies": list(Currency),
}
