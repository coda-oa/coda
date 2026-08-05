from datetime import date
from decimal import Decimal
from typing import Any

from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.mappers._domain import ContractDomainMapper
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services import invoice_service
from coda.domain.contract import Contract, ContractYear, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory

from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import ContractItem, PublicationItem
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


def create_contract_and_year() -> tuple[Contract, ContractModel, ContractYear]:
    contract, contract_model = create_contract_with_model()
    contract_year = domainfactory.contract_year(contract)
    return contract, contract_model, contract_year


def create_invoice_with_funded_position(contract_year: ContractYear) -> None:
    position = invoice_positions.create(
        item=ContractItem(contract_year, cost_type=ContractCostType.Publish),
        cost=Money(Decimal("3000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id="POS-001",
    )
    budget_a = modelfactory.budget(name="Budget A")
    budget_b = modelfactory.budget(name="Budget B")
    budget_c = modelfactory.budget(name="Budget C")
    position.assign_funding(Budget(FundingSourceId(budget_a.pk), budget_a.name), Decimal("1000.00"))
    position.assign_funding(Budget(FundingSourceId(budget_b.pk), budget_b.name), Decimal("1200.00"))
    position.assign_funding(Budget(FundingSourceId(budget_c.pk), budget_c.name), Decimal("800.00"))
    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position])
    invoice_service.save(invoice)


def create_invoices_with_positions(
    contract_year: ContractYear,
) -> tuple[Invoice, Invoice]:
    position1 = domainfactory.contract_position(contract_year)
    creditor = modelfactory.creditor()
    invoice1 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position1])
    invoice_service.save(invoice1)
    position2 = domainfactory.contract_position(contract_year)
    budget_x = modelfactory.budget(name="Budget X")
    budget_y = modelfactory.budget(name="Budget Y")
    position2.assign_funding(
        Budget(FundingSourceId(budget_x.pk), budget_x.name),
        position2.cost.amount * Decimal("0.6"),
    )
    position2.assign_remaining(Budget(FundingSourceId(budget_y.pk), budget_y.name))
    invoice2 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position2])
    invoice_service.save(invoice2)
    return invoice1, invoice2


def create_contract_with_model() -> tuple[Contract, ContractModel]:
    contract = domainfactory.contract()
    publisher = modelfactory.publisher(name="Test Publisher")
    journal = modelfactory.journal(title="Test Journal")
    contract.publishers = [PublisherId(publisher.id)]
    contract.journals = [JournalId(journal.id)]
    contract.id = contract_repository.create(contract)
    assert contract.id is not None
    contract_model = ContractModel.objects.get(pk=int(contract.id))
    return contract, contract_model


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
