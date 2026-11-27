from collections.abc import Iterable
from dataclasses import dataclass

from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository
from coda.apps.invoices.mappers import FundingSourceDomainMapper
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource


@dataclass
class FundingSourceStaging:
    legacy: dict[str, FundingSource]
    assignments: dict[str, FundingSource]

    def commit(self, referenced: Iterable[FundingSource]) -> None:
        pending = [source for source in referenced if source.id is None]
        if not pending:
            return

        unique_by_key: dict[tuple[str, str], FundingSource] = {}
        for source in pending:
            unique_by_key.setdefault(_funding_source_key(source), source)

        keys = list(unique_by_key)
        funding_source_ids = funding_source_repository.create_many(
            unique_by_key[key] for key in keys
        )
        ids_by_key = dict(zip(keys, funding_source_ids))

        for source in pending:
            source.id = ids_by_key[_funding_source_key(source)]


def stage_funding_sources(invoice_dtos: Iterable[InvoiceImportDto]) -> FundingSourceStaging:
    """Resolve and stage funding sources for legacy fields and split assignments."""
    legacy_names = {name for name in _legacy_funding_source_names(invoice_dtos) if name}
    assignment_sources = set(_funding_assignment_sources(invoice_dtos))
    assignment_budget_names = {name for type_, name in assignment_sources if type_ == "budget"}
    institution_names = {name for type_, name in assignment_sources if type_ == "institution"}

    budgets = _stage_budgets(legacy_names | assignment_budget_names)
    splits = _stage_institutions(institution_names)

    assignments: dict[str, FundingSource] = {
        name: budgets[name] for name in assignment_budget_names
    }
    assignments.update({name: splits[name] for name in institution_names if name in splits})

    return FundingSourceStaging(
        legacy={name: budgets[name] for name in legacy_names},
        assignments=assignments,
    )


def _stage_budgets(names: set[str]) -> dict[str, FundingSource]:
    if not names:
        return {}

    existing = FundingSourceModel.objects.filter(type="budget", name__in=names)
    budgets: dict[str, FundingSource] = {
        model.name: FundingSourceDomainMapper.map(model) for model in existing
    }
    for name in names:
        budgets.setdefault(name, Budget.new(name))

    return budgets


def _stage_institutions(names: set[str]) -> dict[str, FundingSource]:
    if not names:
        return {}

    institutions = {
        institution.name: InstitutionId(institution.pk)
        for institution in Institution.objects.filter(name__in=names)
    }

    splits: dict[str, FundingSource] = {}
    if institutions:
        existing = FundingSourceModel.objects.select_related("institution").filter(
            type="institution", institution_id__in=list(institutions.values())
        )
        splits = {
            source.institution.name: FundingSourceDomainMapper.map(source)
            for source in existing
            if source.institution is not None
        }

    for name in names:
        if name in institutions:
            splits.setdefault(name, SplitSource.new(institutions[name], name))

    return splits


def _funding_source_key(source: FundingSource) -> tuple[str, str]:
    return (source.kind(), source.name)


def _legacy_funding_source_names(invoice_dtos: Iterable[InvoiceImportDto]) -> Iterable[str]:
    return (
        position.funding_source
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
    )


def _funding_assignment_sources(
    invoice_dtos: Iterable[InvoiceImportDto],
) -> Iterable[tuple[str, str]]:
    return (
        (assignment.type, assignment.name)
        for invoice_dto in invoice_dtos
        for position in invoice_dto.positions
        for assignment in position.funding_assignments
    )
