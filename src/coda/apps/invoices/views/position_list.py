from collections.abc import Callable
from dataclasses import asdict
from decimal import Decimal
from typing import Any, TypedDict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import render

from coda import formdata
from coda.apps.fundingrequests import repository
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.apps.publications.models import Publication
from coda.contexts.finance.dto.edit_position_dtos import (
    FundingAssignmentDto,
    PositionDto,
    PositionList,
    PublicationItemDto,
    RelatedFundingRequest,
)
from coda.contexts.finance.services import invoice_parser
from coda.contexts.finance.services.invoice_parser._parser import InvoiceTotal
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice_positions import InvalidSplitAmount
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
    position_list = formdata.map_to_model(PositionList, request.POST)
    position_list.positions.extend(added_positions(request))
    return render_positions(request, position_list)


@login_required
def remove_position(request: HttpRequest) -> HttpResponse:
    position_list = formdata.map_to_model(PositionList, request.POST)
    if remove_position := request.POST.get("remove-position"):
        index = int(remove_position) - 1
        position_list.positions.pop(index)

    return render_positions(request, position_list)


@login_required
def invoice_total(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "invoices/position_summary.html",
        asdict(_invoice_total_from_request(request)),
    )


def _invoice_total_from_request(request: HttpRequest) -> InvoiceTotal:
    position_list = formdata.map_to_model(PositionList, request.POST)
    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    try:
        return invoice_parser.invoice_total(position_list.positions, currency)
    except InvalidSplitAmount:
        return InvoiceTotal(Decimal(0), Decimal(0), Decimal(0))


@login_required
def add_funding_assignment(request: HttpRequest) -> HttpResponse:
    position_list = formdata.map_to_model(PositionList, request.POST)
    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["add_funding_assignment_to_position"]) - 1
        position_dto = position_list.positions[position_index]
    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())

    position = invoice_parser.to_position(position_dto, currency)
    if not position.funding_assignments() or position.unassigned_costs().amount > 0:
        position.assign_remaining(None)
        position_dto = invoice_parser.position_to_dto(position)
        position_list.positions[position_index] = position_dto
    else:
        position_dto.funding_assignments.append(FundingAssignmentDto())

    return render_positions(request, position_list)


@login_required
def remove_funding_assignment(request: HttpRequest) -> HttpResponse:
    position_list = formdata.map_to_model(PositionList, request.POST)
    try:
        remove_index = request.POST["remove_funding_assignment"]
        position_index_str, funding_index_str = remove_index.split("::")
        position_index = int(position_index_str) - 1
        funding_index = int(funding_index_str) - 1
        position_list.positions[position_index].funding_assignments.pop(funding_index)
    except (IndexError, KeyError, ValueError):
        # we need to render the position_list no matter what
        # so there is no need to do any additional error handling here
        pass

    return render_positions(request, position_list)


@login_required
def refresh_unassigned_costs(request: HttpRequest) -> HttpResponse:
    errors: ErrorDict | None = None
    try:
        position_list = formdata.map_to_model(PositionList, request.POST)
    except ValueError:
        return render_positions(request, PositionList())

    try:
        position_index_str = request.POST["refresh_position_index"]
        position_index = int(position_index_str) - 1
        position_dto = position_list.positions[position_index]
    except (IndexError, KeyError):
        return render_positions(request, PositionList())

    try:
        position = invoice_parser.to_position(
            position_dto, Currency.from_code(request.POST["currency"])
        )
        position_dto.unassigned_costs = position.unassigned_costs().amount
    except InvalidSplitAmount:
        errors = ErrorDict(
            errors={
                f"positions-{position_index_str}-funding_assignments-errors": "Invalid funding assignment!"
            }
        )

    return render_positions(request, position_list, errors)


@login_required
def switch_funding_source_type(request: HttpRequest) -> HttpResponse:
    key = ""
    for k in request.GET.keys():
        if k.endswith("funding_source_type"):
            key = k
            break

    funding_source_type = request.GET.get(key)
    template_name = "invoices/position_cost_split_funding_source_select_choices.html"
    if funding_source_type == "budget":
        return render(request, template_name, funding_sources_context())
    elif funding_source_type == "institution":
        return render(request, template_name, {"funding_sources": Institution.objects.all()})

    return HttpResponseNotFound()


def added_positions(request: HttpRequest) -> list[PositionDto]:
    _positions = [parser(request) for parser in _ADD_POSITION_PARSERS.values()]
    return [p for p in _positions if p is not None]


def parse_added_publication_position(request: HttpRequest) -> PositionDto | None:
    publication_id = request.POST.get("add-publication-position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return PositionDto(
        item=PublicationItemDto(
            id=publication.pk,
            title=publication.title,
            funding_request=maybe_request_context(publication),
        )
    )


def maybe_request_context(publication: Publication) -> RelatedFundingRequest:
    reference = repository.find_reference_by_publication(PublicationId(publication.pk))
    if reference:
        return RelatedFundingRequest(request_id=reference.request_id, url=reference.url)

    return RelatedFundingRequest()


def render_positions(
    request: HttpRequest, position_list: PositionList, errors: ErrorDict | None = None
) -> HttpResponse:
    errors = errors if errors else {"errors": {}}
    return render(
        request,
        "invoices/invoice_positions.html",
        {"position_list": position_list}
        | _DefaultContext
        | errors
        | funding_sources_context()
        | asdict(_invoice_total_from_request(request)),
    )


def funding_sources_context() -> dict[str, Any]:
    return {"funding_sources": FundingSource.objects.all()}


def _generic_position_parser(prefix: str) -> Callable[[HttpRequest], PositionDto | None]:
    def parse(request: HttpRequest) -> PositionDto | None:
        filtered_by_prefix = {k: v for k, v in request.POST.items() if k.startswith(prefix)}
        if not filtered_by_prefix:
            return None

        return formdata.map_to_model(PositionDto, filtered_by_prefix, prefix=prefix)

    return parse


_ADD_POSITION_PARSERS = {
    "publication": parse_added_publication_position,
    "contract": _generic_position_parser("contract"),
    "free": _generic_position_parser("free-position"),
}


_DefaultContext = {
    "publication_cost_types": _PublicationCostTypes,
    "contract_cost_types": _ContractCostTypes,
    "currencies": list(Currency),
}
