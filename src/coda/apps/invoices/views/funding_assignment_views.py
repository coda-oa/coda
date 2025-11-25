"""Funding assignment CRUD views for invoice positions."""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda import formdata
from coda.contexts.finance.dto.edit_position_dtos import (
    FundingAssignmentDto,
    PositionDto,
    PositionList,
)
from coda.contexts.finance.services import invoice_parser
from coda.domain.finance.invoice_positions import InvalidSplitAmount
from coda.domain.money import Currency

from coda.apps.invoices.views.position_context import funding_sources_context
from coda.apps.invoices.views.position_views import render_positions, render_single_position


@login_required
def add_funding_assignment(request: HttpRequest) -> HttpResponse:
    """Add a funding assignment to a position.

    When no assignments exist, pre-fills with the full position cost.
    When assignments exist, pre-fills with remaining unassigned costs.
    Filters out implicit empty assignments from the template before adding new one.

    Expects position_index in POST data for granular updates.
    Only re-renders the affected position + OOB summary update.
    """
    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["position_index"])

        # Parse only the targeted position using prefix
        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )

        # Process and render single position
        # Filter out implicit assignments (STATE 1) which have amount=0
        # An assignment is explicit if it has a non-zero amount (funding_source can still be None)
        explicit_assignments = [fa for fa in position_dto.funding_assignments if fa.amount != 0]
        position_dto.funding_assignments = explicit_assignments

        if not explicit_assignments:
            position = invoice_parser.to_position(position_dto, currency)
            amount_to_assign = position.cost.amount
        else:
            position = invoice_parser.to_position(position_dto, currency)
            amount_to_assign = position.unassigned_costs().amount

        position_dto.funding_assignments.append(FundingAssignmentDto(amount=amount_to_assign))

        # Recalculate unassigned costs after adding new assignment
        try:
            position = invoice_parser.to_position(position_dto, currency)
            position_dto.unassigned_costs = position.unassigned_costs().amount
        except InvalidSplitAmount:
            position_dto.unassigned_costs = Decimal(0)

        return render_single_position(request, position_dto, position_index)

    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())


@login_required
def remove_funding_assignment(request: HttpRequest) -> HttpResponse:
    """Remove a funding assignment from a position.

    Expects position_index and assignment_index in POST data.
    Only re-renders the affected position + OOB summary update.
    """
    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["position_index"])
        assignment_index = int(request.POST["assignment_index"]) - 1

        # Parse only the targeted position using prefix
        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )

        # Remove the specified assignment
        try:
            position_dto.funding_assignments.pop(assignment_index)
        except IndexError:
            pass  # Assignment doesn't exist, render as-is

        # Recalculate unassigned costs after removal
        try:
            position = invoice_parser.to_position(position_dto, currency)
            position_dto.unassigned_costs = position.unassigned_costs().amount
        except InvalidSplitAmount:
            # If assignments are invalid, set unassigned_costs to 0 to avoid confusion
            position_dto.unassigned_costs = Decimal(0)

        return render_single_position(request, position_dto, position_index)

    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())


@login_required
def refresh_unassigned_costs(request: HttpRequest) -> HttpResponse:
    """Recalculate unassigned costs for a position.

    Recalculates unassigned costs based on current funding assignments.
    Returns error if funding assignments are invalid.

    Expects position_index in POST data for granular updates.
    Only re-renders the affected position + OOB summary update.
    """
    errors: dict[str, str] | None = None

    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["position_index"])

        # Parse only the targeted position using prefix
        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )

        # Calculate unassigned costs
        try:
            position = invoice_parser.to_position(position_dto, currency)
            position_dto.unassigned_costs = position.unassigned_costs().amount
        except InvalidSplitAmount:
            errors = {
                f"positions-{position_index}-funding_assignments-errors": "Invalid funding assignment!"
            }

        return render_single_position(request, position_dto, position_index, errors)

    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())


@login_required
def switch_funding_source_type(request: HttpRequest) -> HttpResponse:
    """Switch funding source type dropdown options.

    HTMX endpoint that returns updated <option> elements based on selected
    funding source type (budget/institution).
    """
    key = ""
    for k in request.GET.keys():
        if k.endswith("funding_source_type"):
            key = k
            break

    funding_source_type = request.GET.get(key)
    template_name = "invoices/funding_source_options.html"
    return render(
        request,
        template_name,
        funding_sources_context() | {"split_funding_source_type": funding_source_type},
    )
