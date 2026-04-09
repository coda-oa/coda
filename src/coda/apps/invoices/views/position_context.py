"""Context building functions for invoice position views."""

from typing import Any

from coda.apps.invoices.models import FundingSource
from coda.contexts.finance.dto.edit_position_dtos import PositionDto
from coda.contexts.finance.services.funding_source_service import (
    get_institutions_allowed_as_funding_source,
)
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.money import Currency

_PublicationCostTypes = [ct.value for ct in PublicationCostType]
_ContractCostTypes = [ct.value for ct in ContractCostType]


def funding_sources_context(for_positions: list[PositionDto] | None = None) -> dict[str, Any]:
    """Build context with funding sources and institutions.

    Args:
        for_positions: Optional list of positions to check for institution usage.
                      Archived institutions used in these positions will be included.

    Returns dictionary containing:
    - funding_sources: Budget-type FundingSource queryset
    - institutions: Institution iterable (includes used archived institutions)
    - default_funding_source_type: Default type ("budget")
    """
    return {
        "funding_sources": FundingSource.objects.filter(type="budget"),
        "institutions": get_institutions_allowed_as_funding_source(for_positions or []),
        "default_funding_source_type": "budget",
    }


DefaultContext: dict[str, Any] = {
    "publication_cost_types": _PublicationCostTypes,
    "contract_cost_types": _ContractCostTypes,
    "currencies": list(Currency),
}
