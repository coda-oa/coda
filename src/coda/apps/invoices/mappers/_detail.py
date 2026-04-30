import datetime
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import cast

from django.db.models import Prefetch, QuerySet
from django.urls import reverse

from coda.apps.invoices.mappers._domain import InvoiceDomainMapper, PositionDomainMapper
from coda.apps.invoices.models import FundingAssignment as FundingAssignmentModel
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.contexts.finance.dto.detail_position_dtos import (
    FundingAssignmentDetailDto,
    PositionDetailDto,
)
from coda.contexts.finance.dto.edit_position_dtos import RelatedFundingRequest
from coda.domain.finance.invoice import Invoice, InvoiceId
from coda.domain.finance.invoice_positions import ContractItem, FreeItem, Position, PublicationItem
from coda.domain.money import Currency, Money


@dataclass
class InvoiceDetail:
    id: int
    url: str
    status: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    currency: Currency
    positions: list[PositionDetailDto]
    tax: Money
    total: Money
    net: Money
    comment: str
    external_invoice_id: str
    conversions: dict[Currency, Decimal]
    unassigned_costs: Decimal

    def with_conversion(self, invoice: Invoice) -> "InvoiceDetail":
        return replace(
            self,
            currency=invoice.currency(),
            positions=[PositionDetailDto.from_position(p) for p in invoice.positions],
            tax=invoice.tax(),
            total=invoice.total(),
            net=invoice.net(),
            unassigned_costs=invoice.unassigned_costs().amount,
        )


class InvoiceDetailMapper:
    @staticmethod
    def prefetch(qs: QuerySet[InvoiceModel], prefix: str = "") -> QuerySet[InvoiceModel]:
        qs = InvoiceDomainMapper.prefetch_invoice_fields(qs)
        qs = qs.prefetch_related(
            Prefetch(
                "positions",
                PositionModel.objects.select_related(
                    "contract",
                    "publication__fundingrequest",
                ).prefetch_related(
                    Prefetch(
                        "funding_assignments",
                        FundingAssignmentModel.objects.select_related(
                            "funding_source__institution"
                        ),
                    )
                ),
            ),
        )
        return qs

    @staticmethod
    def map(model: InvoiceModel) -> InvoiceDetail:
        invoice = InvoiceDomainMapper.map(model)
        id = cast(InvoiceId, invoice.id)

        return InvoiceDetail(
            id=id,
            url=reverse("invoices:detail", kwargs={"pk": id}),
            status=invoice.status.name,
            number=invoice.number,
            date=invoice.date,
            creditor=invoice.creditor,
            creditor_name=model.creditor.name,
            currency=invoice.currency(),
            positions=[
                _map_position_dto(pos_model) for pos_model in model.positions.order_by("id")
            ],
            tax=invoice.tax(),
            total=invoice.total(),
            net=invoice.net(),
            comment=invoice.comment,
            external_invoice_id=invoice.external_invoice_id,
            conversions=invoice.conversions(),
            unassigned_costs=invoice.unassigned_costs().amount,
        )


def _map_position_dto(model: PositionModel) -> PositionDetailDto:
    position = PositionDomainMapper.map(model)
    funding_assignments = _map_funding_assignments(position)
    tax_amount = position.tax().amount
    net_costs = position.net().amount
    tax_rate = position.tax_rate.percentage()

    if isinstance(position.item, ContractItem):
        contract_year = position.item.item
        contract_id = contract_year.contract_id
        name = model.contract.name if model.contract else str(contract_id)
        error = (
            "Contract year is outside of contract period"
            if not contract_year.is_in_contract_period()
            else ""
        )
        return PositionDetailDto(
            type="contract",
            title=f"{name} ({contract_year.year})",
            url=reverse("contracts:detail", kwargs={"pk": contract_id}) if contract_id else "",
            cost_type=position.item.cost_type.value,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            net_costs=net_costs,
            funding_assignments=funding_assignments,
            error=error,
        )

    if isinstance(position.item, PublicationItem):
        pub_model = model.publication
        title = pub_model.title if pub_model else str(position.item.item)
        fr_model = getattr(pub_model, "fundingrequest", None) if pub_model else None
        funding_request = (
            RelatedFundingRequest(request_id=fr_model.request_id, url=fr_model.get_absolute_url())
            if fr_model
            else RelatedFundingRequest()
        )
        return PositionDetailDto(
            type="publication",
            title=title,
            url=funding_request.url,
            cost_type=position.item.cost_type.value,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            net_costs=net_costs,
            funding_assignments=funding_assignments,
        )

    assert isinstance(position.item, FreeItem)
    return PositionDetailDto(
        type="free",
        title=position.item.item,
        url="",
        cost_type=position.item.cost_type.value,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        net_costs=net_costs,
        funding_assignments=funding_assignments,
    )


def _map_funding_assignments(position: Position) -> list[FundingAssignmentDetailDto]:
    return [
        FundingAssignmentDetailDto(
            funding_source_id=fa.funding_source.id if fa.funding_source else None,
            funding_source_name=fa.funding_source.name if fa.funding_source else "unspecified",
            amount=fa.amount.amount,
        )
        for fa in position.funding_assignments()
    ]
