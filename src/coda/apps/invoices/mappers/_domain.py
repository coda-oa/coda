from typing import TypedDict

from django.db.models import Model, Prefetch, QuerySet

from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.invoices.models import FundingAssignment as FundingAssignmentModel
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.apps.mappers import prefixed
from coda.coda_itertools import LazyCachedIterable
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractYear
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
    Position,
    PositionItemType,
    PublicationItem,
)
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId


class InvoiceDomainMapper:
    @staticmethod
    def prefetch(qs: QuerySet[InvoiceModel], prefix: str = "") -> QuerySet[InvoiceModel]:
        qs = InvoiceDomainMapper.prefetch_invoice_fields(qs)
        qs = PositionDomainMapper.prefetch(qs, "positions")
        return qs

    @staticmethod
    def prefetch_invoice_fields(qs: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
        return qs.select_related("creditor").prefetch_related("currency_conversions")

    @staticmethod
    def map(model: InvoiceModel) -> Invoice:
        invoice = Invoice(
            id=InvoiceId(model.pk),
            date=model.date,
            number=model.number,
            creditor=CreditorId(model.creditor.pk),
            status=PaymentStatus(model.status),
            positions=LazyCachedIterable(
                PositionDomainMapper.map(position) for position in model.positions.order_by("id")
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


class PositionDomainMapper:
    @staticmethod
    def prefetch[_T: Model](qs: QuerySet[_T], prefix: str = "") -> QuerySet[_T]:
        if prefix:
            qs = qs.prefetch_related(
                Prefetch(prefix, PositionModel.objects.select_related("contract"))
            )
        else:
            qs = qs.select_related("contract")

        return qs.prefetch_related(
            Prefetch(
                prefixed(prefix, "funding_assignments"),
                FundingAssignmentModel.objects.select_related("funding_source__institution"),
            ),
        )

    @staticmethod
    def map(position: PositionModel) -> Position:
        item = _get_item_from_position_model(position)
        common_args = _extract_common_position_args(position)
        _position = invoice_positions.create(item=item, **common_args)

        for funding in position.funding_assignments.all():
            _position.assign_funding(
                (
                    FundingSourceDomainMapper.map(funding.funding_source)
                    if funding.funding_source
                    else None
                ),
                funding.amount,
            )

        return _position


class FundingSourceDomainMapper:
    @staticmethod
    def prefetch[_T: Model](qs: QuerySet[_T], prefix: str = "") -> QuerySet[_T]:
        return qs.select_related(prefixed(prefix, "institution"))

    @staticmethod
    def map(model: FundingSourceModel) -> FundingSource:
        if model.type == "budget":
            return Budget(FundingSourceId(model.pk), model.name)
        elif model.type == "institution":
            assert model.institution is not None
            return SplitSource(
                FundingSourceId(model.pk),
                InstitutionId(model.institution.pk),
                model.institution.name,
            )
        raise ValueError("Invalid model type")


def _extract_common_position_args(position: PositionModel) -> "_CommonPositionArgs":
    return {
        "cost": Money(position.cost_amount, Currency[position.cost_currency]),
        "tax_rate": TaxRate(position.tax_rate),
        "external_position_id": position.external_position_id,
    }


def _get_item_from_position_model(position: PositionModel) -> PositionItemType:
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


class _CommonPositionArgs(TypedDict):
    cost: Money
    tax_rate: TaxRate
    external_position_id: str
