"""Context building functions for invoice position views."""

from typing import Any

from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.money import Currency

_PublicationCostTypes = [ct.value for ct in PublicationCostType]
_ContractCostTypes = [ct.value for ct in ContractCostType]


def funding_sources_context() -> dict[str, Any]:
    """Build context with funding sources and institutions.

    Returns dictionary containing:
    - funding_sources: Budget-type FundingSource queryset
    - institutions: All Institution queryset
    - default_funding_source_type: Default type ("budget")
    """
    return {
        "funding_sources": FundingSource.objects.filter(type="budget"),
        "institutions": Institution.objects.all(),
        "default_funding_source_type": "budget",
    }


DefaultContext: dict[str, Any] = {
    "publication_cost_types": _PublicationCostTypes,
    "contract_cost_types": _ContractCostTypes,
    "currencies": list(Currency),
}
