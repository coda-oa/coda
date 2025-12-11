from decimal import Decimal
from typing import TypedDict, cast

from django.urls import reverse

from coda.apps.contracts import mapper as contract_mapper
from coda.apps.invoices import models as invoice_models
from coda.coda_itertools import LazyCachedIterable
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import (
    CreditorId,
    FundingSourceId,
    Invoice,
    InvoiceId,
    PaymentStatus,
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
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId


def as_domain_object(model: invoice_models.Invoice) -> Invoice:
    """Convert InvoiceModel to Invoice domain object."""
    invoice = Invoice(
        id=InvoiceId(model.pk),
        date=model.date,
        number=model.number,
        creditor=CreditorId(model.creditor.pk),
        status=PaymentStatus(model.status),
        positions=LazyCachedIterable(
            _as_position_domain_object(position) for position in model.positions.all()
        ),
        comment=model.comment,
        external_invoice_id=model.external_invoice_id,
    )

    conversions = model.currency_conversions.all()
    for conversion in conversions:
        invoice.add_conversion(
            conversion.exchange_rate, Currency.from_code(conversion.target_currency)
        )

    return invoice


def as_list_item(model: invoice_models.Invoice) -> InvoiceListItem:
    """
    Convert InvoiceModel to InvoiceListItem using pre-computed annotations.
    This version relies on database-level calculations for maximum performance.
    """

    net_amount = getattr(model, "net_total", Decimal("0"))
    tax_amount = getattr(model, "tax_total", Decimal("0"))
    total_amount = net_amount + tax_amount

    currency_code = getattr(model, "first_position_currency", "EUR")
    currency = Currency.from_code(currency_code)

    net = Money(net_amount, currency)
    tax = Money(tax_amount, currency)
    total = Money(total_amount, currency)

    conversions = {}
    for conversion in model.currency_conversions.all():
        conversions[Currency.from_code(conversion.target_currency)] = conversion.exchange_rate

    creditor_name = model.creditor.name

    url = reverse("invoices:detail", kwargs={"pk": model.pk})

    return InvoiceListItem(
        id=InvoiceId(model.pk),
        number=model.number,
        date=model.date,
        creditor=CreditorId(model.creditor.pk),
        creditor_name=creditor_name,
        status=PaymentStatus(model.status),
        currency=currency,
        net=net,
        tax=tax,
        total=total,
        comment=model.comment,
        external_invoice_id=model.external_invoice_id,
        conversions=conversions,
        url=url,
    )


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
        return SplitSource(
            FundingSourceId(model.pk),
            cast(InstitutionId, model.institution_id),
            model.name,
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
        contract = contract_mapper.as_domain_object(position.contract)
        return ContractItem(
            contract.in_year(position.contract_year), ContractCostType(position.cost_type)
        )
    elif position.publication:
        return PublicationItem(
            PublicationId(position.publication.pk), PublicationCostType(position.cost_type)
        )
    else:
        return FreeItem(position.description, PublicationCostType(position.cost_type))


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
