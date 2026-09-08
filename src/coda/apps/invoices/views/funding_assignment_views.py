"""Funding assignment CRUD views for invoice positions."""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from coda import formdata
from coda.apps.invoices.views.position_context import funding_sources_context
from coda.apps.invoices.views.position_parsers import PositionDtoWithErrors
from coda.apps.invoices.views.position_views import render_positions, render_single_position
from coda.contexts.finance.dto.edit_position_dtos import (
    FundingAssignmentDto,
    PositionDto,
    PositionList,
)
from coda.contexts.finance.services.invoice_import import position_to_dto, to_position
from coda.domain.finance.invoice_positions import InvalidSplitAmount
from coda.domain.finance.taxable_money import CostBasis
from coda.domain.money import Currency


@login_required
@require_POST
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

        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )

        display_mode = CostBasis(position_dto.cost_basis_mode)
        position = to_position(position_dto, currency, parse_safe=True)

        add_empty_assignment = (
            position.unassigned_costs().amount == 0 and len(position.funding_assignments()) != 0
        )
        position.assign_remaining(None)

        unsafe_item = position_dto.item
        position_dto = position_to_dto(position, display_mode)
        position_dto.item = unsafe_item
        if add_empty_assignment:
            position_dto.funding_assignments.append(FundingAssignmentDto(amount=Decimal(0)))

        return render_single_position(request, position_dto, position_index)
    except (IndexError, KeyError, ValueError) as e:
        return HttpResponseBadRequest(str(e))


@login_required
@require_POST
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

        # Get display mode (form values match this mode)
        display_mode = CostBasis(position_dto.cost_basis_mode)

        # Remove the specified assignment
        try:
            position_dto.funding_assignments.pop(assignment_index)
        except IndexError:
            pass  # Assignment doesn't exist, render as-is

        # Recalculate and convert to display mode
        try:
            position = to_position(position_dto, currency, parse_safe=True)
            # Convert back to display mode (domain handles conversion)
            unsafe_item = position_dto.item
            position_dto = position_to_dto(position, display_mode)
            position_dto.item = unsafe_item
        except InvalidSplitAmount:
            # If assignments are invalid, set unassigned_costs to 0 to avoid confusion
            position_dto.unassigned_costs = Decimal(0)

        return render_single_position(request, position_dto, position_index)

    except (IndexError, KeyError, ValueError) as e:
        return HttpResponseBadRequest(str(e))


@login_required
@require_POST
def refresh_unassigned_costs(request: HttpRequest) -> HttpResponse:
    """Recalculate unassigned costs for a position.

    Recalculates unassigned costs based on current funding assignments.
    Returns error if funding assignments are invalid.

    Expects position_index in POST data for granular updates.
    Only re-renders the affected position + OOB summary update.
    """
    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["position_index"])
        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )
    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())

    display_mode = CostBasis(position_dto.cost_basis_mode)

    try:
        # Parser interprets amounts according to display_mode
        position = to_position(position_dto, currency)
        # Convert back to display mode (domain handles conversion)
        position_dto = position_to_dto(position, display_mode)
    except InvalidSplitAmount:
        position_dto = PositionDtoWithErrors.from_dto(position_dto, "Invalid funding assignment")

    return render_single_position(request, position_dto, position_index)


@login_required
@require_POST
def switch_cost_basis_mode(request: HttpRequest) -> HttpResponse:
    """Switch between net and gross display modes for funding assignments.

    Converts assignment amounts between modes for display. Since there are only
    two modes (net and gross), the old mode is always the opposite of the selected mode.

    This endpoint is specifically for mode selector changes. Amount field changes
    should use refresh_unassigned_costs() instead.

    Expects position_index in POST data for granular updates.
    Only re-renders the affected position + OOB summary update.
    """
    try:
        currency = Currency.from_code(request.POST["currency"])
        position_index = int(request.POST["position_index"])

        # Parse position DTO from form
        position_dto = formdata.map_to_model(
            PositionDto, request.POST, prefix=f"positions-{position_index}"
        )

        # Get newly selected mode
        new_mode = CostBasis(position_dto.cost_basis_mode)

        # Since there are only 2 modes, old mode is the opposite of new mode
        old_mode = CostBasis.net if new_mode == CostBasis.gross else CostBasis.gross

        # Form values are in OLD mode, temporarily override for correct parsing
        position_dto.cost_basis_mode = old_mode
        position = to_position(position_dto, currency)

        # Convert to NEW mode for display
        position_dto = position_to_dto(position, new_mode)

        # Ensure cost_basis_mode reflects the selected mode
        position_dto.cost_basis_mode = new_mode

        return render_single_position(request, position_dto, position_index)

    except (IndexError, KeyError, ValueError):
        return render_positions(request, PositionList())


@login_required
@require_GET
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
