"""Position CRUD views for invoice positions."""

from dataclasses import asdict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from coda import formdata
from coda.apps.invoices.views.position_context import DefaultContext, funding_sources_context
from coda.apps.invoices.views.position_parsers import added_positions
from coda.contexts.finance.dto.edit_position_dtos import PositionDto, PositionList
from coda.contexts.finance.services.invoice_parser._parser import InvoiceTotal
from coda.domain.finance.invoice_positions import InvalidSplitAmount
from coda.domain.money import Currency


@login_required
@require_GET
def switch_position_tab(request: HttpRequest) -> HttpResponse:
    """Switch between position tabs (publication/contract/free).

    Renders the add_positions.html template with the selected tab.
    """
    tab = request.GET["tab"]
    return render(
        request,
        "invoices/add_positions.html",
        {
            "tab": tab,
            "publication_cost_types": DefaultContext["publication_cost_types"],
            "contract_cost_types": DefaultContext["contract_cost_types"],
        },
    )


@login_required
@require_POST
def add_position(request: HttpRequest) -> HttpResponse:
    """Add a new position to the position list.

    Parses the current position list from POST data, adds new positions
    parsed from the request, and re-renders the position list.
    """
    position_list = formdata.map_to_model(PositionList, request.POST)
    position_list.positions.extend(added_positions(request))
    return render_positions(request, position_list)


@login_required
@require_POST
def remove_position(request: HttpRequest) -> HttpResponse:
    """Remove a position from the position list.

    Removes the position at the index specified in 'remove-position' POST parameter
    and re-renders the position list.
    """
    position_list = formdata.map_to_model(PositionList, request.POST)
    if remove_position_str := request.POST.get("remove-position"):
        index = int(remove_position_str) - 1
        position_list.positions.pop(index)

    return render_positions(request, position_list)


@login_required
@require_POST
def invoice_total(request: HttpRequest) -> HttpResponse:
    """Calculate and render invoice total.

    Calculates total from all positions and renders the position_summary.html template.
    """
    position_list = formdata.map_to_model(PositionList, request.POST)
    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    total = safe_invoice_total(position_list.positions, currency)
    return render(
        request,
        "invoices/position_summary.html",
        {"position_list": position_list} | asdict(total),
    )


def safe_invoice_total(positions: list[PositionDto], currency: Currency) -> InvoiceTotal:
    """Calculate invoice total from position list and currency.

    Returns InvoiceTotal with calculated amounts, or zero amounts if
    InvalidSplitAmount is raised.
    """
    from coda.contexts.finance.services import invoice_parser

    try:
        return invoice_parser.invoice_total(positions, currency)
    except InvalidSplitAmount:
        return InvoiceTotal(Decimal(0), Decimal(0), Decimal(0))


def render_single_position(
    request: HttpRequest, position_dto: PositionDto, counter: int
) -> HttpResponse:
    """Render a single position.

    The summary is updated independently via its own hx-trigger on cost-amount/cost-type changes.

    Args:
        request: HTTP request (needed for context building)
        position_dto: Position DTO to render
        counter: Position counter (1-indexed)
    """
    context = (
        {
            "position": position_dto,
            "counter": counter,
        }
        | DefaultContext
        | funding_sources_context(position_list.positions)
    )

    return render(request, "invoices/position_single_with_summary.html", context)


def render_positions(request: HttpRequest, position_list: PositionList) -> HttpResponse:
    """Render the position list template.

    Combines position_list with default context, funding sources context,
    errors, and invoice total calculation.

    Note: Calculates invoice total from the provided position_list, not from request.POST.
    This ensures that modifications to position_list (like add/remove operations) are
    reflected in the summary.
    """
    currency = Currency.from_code(request.POST.get("currency", "EUR"))
    invoice_total = safe_invoice_total(position_list.positions, currency)

    return render(
        request,
        "invoices/invoice_positions.html",
        {"position_list": position_list}
        | DefaultContext
        | funding_sources_context(position_list.positions)
        | asdict(invoice_total),
    )
