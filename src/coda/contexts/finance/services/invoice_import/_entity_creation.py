"""Entity creation and retrieval for invoice import.

This module handles finding or creating all related entities needed during
invoice import, including creditors, contracts, funding sources, and
funding assignments.
"""

from collections.abc import Iterable

from coda.apps.contracts import repository as contract_repository
from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.contexts.finance.dto.import_dtos import ContractPositionImportDto, InvoiceImportDto
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.string import NonEmptyStr


def bulk_create_creditors(invoice_dtos: Iterable[InvoiceImportDto]) -> dict[str, CreditorId]:
    """Find or create creditors and return lookup dictionary.

    Args:
        invoice_dtos: Invoice DTOs to extract creditor names from

    Returns:
        Dictionary mapping creditor name to CreditorId
    """
    creditors = set(_creditors(invoice_dtos))
    existing = Creditor.objects.filter(name__in=creditors)
    existing_map = {c.name: c for c in existing}
    to_create = [Creditor(name=name) for name in creditors if name not in existing_map]
    if to_create:
        created = Creditor.objects.bulk_create(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: CreditorId(existing_map[name].pk) for name in creditors}


def bulk_create_funding_sources(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> dict[str, FundingSourceId]:
    """Find or create funding sources and return lookup dictionary.

    Args:
        invoice_dtos: Invoice DTOs to extract funding source names from

    Returns:
        Dictionary mapping funding source name to FundingSourceId
    """
    funding_sources = set(_funding_sources(invoice_dtos))
    existing = FundingSourceModel.objects.filter(name__in=funding_sources)
    existing_map = {fs.name: FundingSourceId(fs.pk) for fs in existing}
    to_create = [
        FundingSourceModel(name=name) for name in funding_sources if name not in existing_map
    ]
    if to_create:
        created = FundingSourceModel.objects.bulk_create(to_create)
        existing_map.update({fs.name: FundingSourceId(fs.pk) for fs in created})

    return existing_map


def find_contracts(invoice_dtos: Iterable[InvoiceImportDto]) -> dict[str, Contract]:
    """Find or create contracts and return lookup dictionary.

    Args:
        invoice_dtos: Invoice DTOs to extract contract names from

    Returns:
        Dictionary mapping contract name to Contract domain object
    """
    contracts = set(_contracts(invoice_dtos))
    existing = contract_repository.find_all_by_names(contracts)
    existing_map: dict[str, Contract] = {c.name: c for c in existing}
    to_create = [
        Contract.new(name=NonEmptyStr(name)) for name in contracts if name not in existing_map
    ]
    if to_create:
        created = contract_repository.create_many(to_create)
        existing_map.update({c.name: c for c in created})
    return {name: existing_map[name] for name in contracts}


def build_funding_assignments_lookup(
    invoice_dtos: list[InvoiceImportDto],
) -> dict[str, FundingSource]:
    """Build lookup of funding sources for split assignments, creating them if needed.

    Note: Invoices referencing non-existent institutions are filtered out during
    early validation, so all institutions referenced here should exist.
    All budgets are created unconditionally.

    Args:
        invoice_dtos: Invoice DTOs to extract funding assignments from

    Returns:
        Dictionary mapping assignment name to FundingSource domain object
    """
    # Collect all unique (type, name) pairs
    unique_assignments = set(_funding_assignment_sources(invoice_dtos))
    if not unique_assignments:
        return {}

    # Separate budgets and institutions
    budgets = [name for type_, name in unique_assignments if type_ == "budget"]
    institutions_names = [name for type_, name in unique_assignments if type_ == "institution"]

    # Build domain objects for creation
    funding_sources_to_create: list[FundingSource] = []
    lookup_keys: list[str] = []

    # Add budgets
    for name in budgets:
        funding_sources_to_create.append(Budget.new(name))
        lookup_keys.append(name)

    # Add institutions (need to fetch institution IDs first)
    if institutions_names:
        institutions = {
            inst.name: InstitutionId(inst.pk)
            for inst in Institution.objects.filter(name__in=institutions_names)
        }
        for name in institutions_names:
            if name in institutions:
                funding_sources_to_create.append(SplitSource.new(institutions[name], name))
                lookup_keys.append(name)

    # Bulk create funding sources
    if not funding_sources_to_create:
        return {}

    funding_source_ids = funding_source_repository.create_many(funding_sources_to_create)

    # Assign IDs back to domain objects
    for funding_source, funding_source_id in zip(funding_sources_to_create, funding_source_ids):
        funding_source.id = funding_source_id

    # Return lookup by name
    return {name: fs for name, fs in zip(lookup_keys, funding_sources_to_create)}


def _creditors(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    """Extract unique creditor names from invoice DTOs."""
    return (invoice_dto.creditor for invoice_dto in invoice_dtos if invoice_dto.creditor)


def _funding_sources(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    """Extract unique funding source names from invoice DTOs."""
    return (
        position.funding_source
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
    )


def _contracts(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    """Extract unique contract names from invoice DTOs."""
    return (
        position.contract_name
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )


def _funding_assignment_sources(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> Iterable[tuple[str, str]]:
    """Extract unique (type, name) pairs for funding assignments from invoice DTOs."""
    return (
        (fa.type, fa.name)
        for invoice in invoice_dtos
        for position in invoice.positions
        for fa in position.funding_assignments
    )
