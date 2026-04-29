from typing import TypedDict, cast


from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.invoices import models as invoice_models
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractYear
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import (
    FundingSourceId,
    Invoice,
)
from coda.domain.finance.invoice_positions import (
    ContractItem,
    FreeItem,
    FundingAssignment,
    Position,
    PositionItemType,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId


def as_django_model(invoice: Invoice) -> invoice_models.Invoice:
    """Convert Invoice domain object to InvoiceModel."""
    return invoice_models.Invoice(
        pk=invoice.id,
        number=invoice.number,
        date=invoice.date,
        creditor_id=invoice.creditor,
        comment=invoice.comment,
        status=invoice.status.value,
        external_invoice_id=invoice.external_invoice_id,
    )


def _as_position_django_model(
    invoice_model: invoice_models.Invoice, position: Position
) -> invoice_models.Position:
    """Convert position domain object to PositionModel."""
    match position.item:
        case ContractItem(contract_year, cost_type):
            return invoice_models.Position(
                contract_id=contract_year.contract.id,
                contract_year=contract_year.year,
                cost_amount=position.cost.amount,
                cost_currency=position.cost.currency.code,
                cost_type=cost_type.value,
                tax_rate=position.tax_rate,
                invoice_id=invoice_model.pk,
                external_position_id=position.external_position_id,
            )
        case PublicationItem(pub_id, cost_type):
            return invoice_models.Position(
                publication_id=pub_id,
                cost_amount=position.cost.amount,
                cost_currency=position.cost.currency.code,
                cost_type=cost_type.value,
                tax_rate=position.tax_rate,
                invoice_id=invoice_model.pk,
                external_position_id=position.external_position_id,
            )
        case FreeItem(description, cost_type):
            return invoice_models.Position(
                description=description,
                cost_amount=position.cost.amount,
                cost_currency=position.cost.currency.code,
                cost_type=cost_type.value,
                tax_rate=position.tax_rate,
                invoice_id=invoice_model.pk,
                external_position_id=position.external_position_id,
            )
        case _:
            raise ValueError("Invalid position item")


class _CommonPositionArgs(TypedDict):
    cost: Money
    tax_rate: TaxRate
    external_position_id: str


def synchronize_relationships(invoice: Invoice, invoice_model: invoice_models.Invoice) -> None:
    """Synchronize relationships (positions and conversions) between domain object and model."""
    invoice_model.positions.all().delete()
    invoice_model.currency_conversions.all().delete()

    positions = [
        _as_position_django_model(invoice_model, position) for position in invoice.positions
    ]
    invoice_models.Position.objects.bulk_create(positions)

    conversions = _create_currency_conversions(invoice, invoice_model)
    invoice_models.CurrencyConversion.objects.bulk_create(conversions)
    funding_source_lookup = _resolve_institution_funding_sources(
        [fa for position in invoice.positions for fa in position.funding_assignments()]
    )

    funding_assignments = [
        invoice_models.FundingAssignment(
            position=position_model,
            funding_source_id=_funding_source_id(funding.funding_source, funding_source_lookup),
            amount=funding.amount.amount,
        )
        for position, position_model in zip(invoice.positions, positions)
        for funding in position.funding_assignments()
    ]
    invoice_models.FundingAssignment.objects.bulk_create(funding_assignments)


def as_domain_funding_source(model: invoice_models.FundingSource) -> FundingSource:
    if model.type == "budget":
        return Budget(FundingSourceId(model.pk), model.name)
    elif model.type == "institution":
        assert model.institution is not None
        return SplitSource(
            FundingSourceId(model.pk),
            cast(InstitutionId, model.institution.pk),
            model.institution.name,
        )
    raise ValueError("Invalid model type")


def _resolve_institution_funding_sources(
    funding_assignments: list[FundingAssignment],
) -> dict[InstitutionId, FundingSourceId]:
    institution_assignments = {
        f.funding_source.institution: f.funding_source.name
        for f in funding_assignments
        if isinstance(f.funding_source, SplitSource)
    }

    existing = invoice_models.FundingSource.objects.filter(
        institution_id__in=institution_assignments.keys(), type="institution"
    )
    existing_map = {
        InstitutionId(fs.institution_id): FundingSourceId(fs.pk)
        for fs in existing
        if fs.institution_id
    }

    created = invoice_models.FundingSource.objects.bulk_create(
        invoice_models.FundingSource(type="institution", institution_id=institution, name=name)
        for institution, name in institution_assignments.items()
        if institution not in existing_map
    )

    return existing_map | {
        InstitutionId(fs.institution_id): FundingSourceId(fs.pk)
        for fs in created
        if fs.institution_id
    }


def _funding_source_id(
    fs: FundingSource | None, lookup: dict[InstitutionId, FundingSourceId]
) -> FundingSourceId | None:
    if not fs:
        return None

    if isinstance(fs, Budget):
        if not fs.id:
            raise ValueError(f"Attempting to save position with unsaved funding source {fs}")

        return fs.id
    elif isinstance(fs, SplitSource):
        return lookup[fs.institution]


def _as_position_domain_object(position: invoice_models.Position) -> Position:
    """Convert PositionModel to position domain object."""
    item = _get_item_from_position_model(position)
    common_args = _extract_common_position_args(position)
    _position = invoice_positions.create(item=item, **common_args)

    for funding in position.funding_assignments.all():
        _position.assign_funding(
            as_domain_funding_source(funding.funding_source) if funding.funding_source else None,
            funding.amount,
        )

    return _position


def _extract_common_position_args(position: invoice_models.Position) -> _CommonPositionArgs:
    """Extract common position arguments from PositionModel."""
    return {
        "cost": Money(position.cost_amount, Currency[position.cost_currency]),
        "tax_rate": TaxRate(position.tax_rate),
        "external_position_id": position.external_position_id,
    }


def _get_item_from_position_model(position: invoice_models.Position) -> PositionItemType:
    """Extract item from PositionModel."""
    if position.contract and position.contract_year:
        contract = ContractDomainMapper.map(position.contract)
        return ContractItem(
            ContractYear(position.contract_year, contract), ContractCostType(position.cost_type)
        )
    elif position.publication:
        return PublicationItem(
            PublicationId(position.publication.pk), PublicationCostType(position.cost_type)
        )
    else:
        return FreeItem(position.description, PublicationCostType(position.cost_type))


def synchronize_relationships_bulk(
    invoices: list[Invoice], models: list[invoice_models.Invoice]
) -> None:
    """Synchronize relationships for multiple invoices in bulk.

    Optimized for bulk import - assumes newly created invoices (no existing relationships).
    Collects all positions, conversions, and funding assignments across all invoices and
    creates them in 3 bulk operations instead of 5N queries (for N invoices).

    This function should only be used for bulk_create() operations where invoices are
    known to be newly created. For single invoices or updates, use synchronize_relationships().

    Query count:
    - Old approach (N invoices): 5N queries (2N DELETEs + 3N INSERTs)
    - New approach (N invoices): 3 queries (3 INSERTs, 0 DELETEs needed)

    Args:
        invoices: List of Invoice domain objects
        models: List of corresponding InvoiceModel instances (must be in same order)
    """
    if not invoices:
        return

    if len(invoices) != len(models):
        raise ValueError(
            f"Invoice and model lists must have same length "
            f"(got {len(invoices)} invoices, {len(models)} models)"
        )

    # Collect all positions across all invoices
    all_positions: list[invoice_models.Position] = []
    position_counts: list[int] = []  # Track number of positions per invoice for indexing

    for invoice, invoice_model in zip(invoices, models):
        invoice_positions = [
            _as_position_django_model(invoice_model, position) for position in invoice.positions
        ]
        all_positions.extend(invoice_positions)
        position_counts.append(len(invoice_positions))

    # Bulk create all positions (Query 1 or 0 if no positions)
    created_positions: list[invoice_models.Position] = []
    if all_positions:
        created_positions = list(invoice_models.Position.objects.bulk_create(all_positions))

    # Collect all currency conversions across all invoices
    all_conversions: list[invoice_models.CurrencyConversion] = []
    for invoice, invoice_model in zip(invoices, models):
        all_conversions.extend(_create_currency_conversions(invoice, invoice_model))

    # Bulk create all conversions (Query 2 or 0 if no conversions)
    if all_conversions:
        invoice_models.CurrencyConversion.objects.bulk_create(all_conversions)

    # Resolve all institution funding sources once across all invoices
    all_funding_assignments_to_resolve = [
        fa
        for invoice in invoices
        for position in invoice.positions
        for fa in position.funding_assignments()
    ]
    funding_source_lookup = _resolve_institution_funding_sources(all_funding_assignments_to_resolve)

    # Collect all funding assignments across all invoices
    all_funding_assignments: list[invoice_models.FundingAssignment] = []
    position_idx = 0

    for invoice, count in zip(invoices, position_counts):
        for position in invoice.positions:
            # Get the corresponding created position model
            position_model = created_positions[position_idx]
            position_idx += 1

            # Create funding assignments for this position
            for funding in position.funding_assignments():
                all_funding_assignments.append(
                    invoice_models.FundingAssignment(
                        position=position_model,
                        funding_source_id=_funding_source_id(
                            funding.funding_source, funding_source_lookup
                        ),
                        amount=funding.amount.amount,
                    )
                )

    # Bulk create all funding assignments (Query 3 or 0 if no funding assignments)
    if all_funding_assignments:
        invoice_models.FundingAssignment.objects.bulk_create(all_funding_assignments)


def _create_currency_conversions(
    invoice: Invoice, invoice_model: invoice_models.Invoice
) -> list[invoice_models.CurrencyConversion]:
    """Create CurrencyConversion objects from invoice domain object."""
    return [
        invoice_models.CurrencyConversion(
            invoice=invoice_model,
            target_currency=target_currency.code,
            exchange_rate=exchange_rate,
        )
        for target_currency, exchange_rate in invoice.conversions().items()
    ]
