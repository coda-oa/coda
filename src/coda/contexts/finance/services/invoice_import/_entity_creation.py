"""Entity resolution for invoice import.

Handles read-only or staged lookups for contracts and publications. Funding
sources live in `_funding_sources.py`, creditors commit through the invoices
app repository.
"""

from collections.abc import Iterable
from typing import cast

from django.db.models import Q

from coda.apps.fundingrequests.models import FundingRequest
from coda.contexts.finance.dto.import_dtos import (
    ContractPositionImportDto,
    InvoiceImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.fundingrequest.dto.import_dtos import ContractImportDto
from coda.contexts.shared.import_service.contract_lookup import (
    contract_periods,
    find_contracts,
)
from coda.domain.contract import Contract
from coda.domain.publication.publication import PublicationId
from coda.domain.string import NonEmptyStr


def build_contract_lookup(invoice_dtos: Iterable[InvoiceImportDto]) -> dict[str, Contract]:
    """Resolve existing contracts and stage id-less contracts for missing names."""
    periods = contract_periods(_contracts(invoice_dtos))
    if not periods:
        return {}

    lookup = find_contracts(periods)
    for name, period in periods.items():
        lookup.setdefault(name, Contract.new(name=NonEmptyStr(name), period=period))

    return lookup


def build_publication_lookup(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> dict[str, PublicationId]:
    """Build lookup mapping request IDs to publication IDs.

    Note: Assumes all publications exist. Call find_invoices_with_missing_publications()
    first to validate.

    Args:
        invoice_dtos: Invoice DTOs to extract request IDs from

    Returns:
        Dictionary mapping request_id to PublicationId
    """
    # Extract request IDs from publication positions
    request_ids = {
        cast(str, position.request_id or position.legacy_request_id)
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        if isinstance(position, PublicationPositionImportDto)
    }

    if not request_ids:
        return {}

    # Query funding requests with publications
    requests = FundingRequest.objects.filter(
        Q(request_id__in=request_ids) | Q(legacy_request_id__in=request_ids)
    ).prefetch_related("publication")

    # Build lookup for both request_id and legacy_request_id
    return {req.request_id: PublicationId(req.publication.id) for req in requests} | {
        req.legacy_request_id: PublicationId(req.publication.id)
        for req in requests
        if req.legacy_request_id
    }


def _contracts(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[ContractImportDto]:
    """Extract unique contract names from invoice DTOs."""
    return (
        ContractImportDto(name=position.contract_name, year=position.contract_year)
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )
