from datetime import date
from decimal import Decimal
from typing import Any

from coda.apps.contracts.mappers._domain import ContractDomainMapper
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services import invoice_service
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory

from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def _make_params(
    period_start: date,
    period_end: date,
    **kwargs: Any,
) -> FundingRequestSearchParams:
    return FundingRequestSearchParams(
        date_range=DateRange(period_start, period_end),
        **kwargs,
    )


def create_funding_request(
    title: str = "Test Publication", request_date: date | None = None
) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    if request_date:
        funding_request.request_date = request_date
        funding_request.save()
    return funding_request


def create_invoice_with_publication_position(funding_request: FundingRequest) -> Invoice:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position = domainfactory.publication_position(PublicationId(funding_request.publication.id))
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])
    invoice.id = invoice_service.save(invoice)

    return invoice


def create_invoice_with_contract_position(contract_year: "ContractYear") -> Invoice:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position = domainfactory.contract_position(contract_year)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])
    invoice.id = invoice_service.save(invoice)

    return invoice


def create_invoice_with_free_position() -> Invoice:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position = domainfactory.free_position()
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])
    invoice.id = invoice_service.save(invoice)

    return invoice


def create_invoice_with_funding_assignments(
    funding_request: FundingRequest,
    cost_amount: Decimal = Decimal("1500.00"),
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
    budget_amount: Decimal = Decimal("1000.00"),
    institution_amount: Decimal = Decimal("500.00"),
) -> "Invoice":
    """Create an invoice with two funding assignments (budget + institution)."""

    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType(cost_type),
        ),
        cost=Money(cost_amount, Currency.EUR),
        tax_rate=TaxRate.from_percentage(int(tax_rate * 100)),
        external_position_id="POS-001",
    )

    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])

    institution = modelfactory.institution()
    funding_source_1 = domainfactory.budget()
    funding_source_2 = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    funding_source_1.id = funding_source_repository.create(funding_source_1)
    funding_source_2.id = funding_source_repository.create(funding_source_2)

    position.assign_funding(funding_source_1, budget_amount)
    position.assign_funding(funding_source_2, institution_amount)

    invoice.id = invoice_service.save(invoice)

    return invoice


def create_invoice_with_currency_conversion(
    target_currency: Currency = Currency.USD,
    exchange_rate: Decimal = Decimal("1.2500"),
) -> Invoice:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[],
    )

    invoice.add_conversion(exchange_rate, target_currency)

    invoice.id = invoice_service.save(invoice)
    return invoice


def create_invoice_with_mixed_positions(funding_request: FundingRequest) -> "Invoice":

    publication_position = domainfactory.publication_position(
        PublicationId(funding_request.publication.id)
    )

    contract = ContractDomainMapper.map(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    contract_position = domainfactory.contract_position(contract_year)

    free_position = domainfactory.free_position()

    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[publication_position, contract_position, free_position],
    )
    invoice.id = invoice_service.save(invoice)

    return invoice
