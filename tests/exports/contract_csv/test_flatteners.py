from decimal import Decimal

import pytest
from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.exports.services.contract_csv.flatteners import flatten_contract_data
from coda.apps.exports.services.contract_csv.mappers import map_contract_to_export_dto
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.domain.contract import Contract, PublisherId
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.finance.invoice_positions import ContractItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import JournalId
from coda.contexts.finance.services import invoice_service
from tests import domainfactory, modelfactory
from tests.exports.fundingrequest_csv.helpers import create_invoice_with_contract_position


def _create_contract_with_model() -> tuple[Contract, ContractModel]:
    contract = domainfactory.contract()
    publisher = modelfactory.publisher(name="Test Publisher")
    journal = modelfactory.journal(title="Test Journal")
    contract.publishers = [PublisherId(publisher.id)]
    contract.journals = [JournalId(journal.id)]
    contract.id = contract_repository.create(contract)
    assert contract.id is not None
    contract_model = ContractModel.objects.get(pk=int(contract.id))
    return contract, contract_model


@pytest.mark.django_db
def test__contract_with_single_invoice_position_without_split__flatten_to_csv__creates_one_csv_row() -> (
    None
):
    contract, contract_model = _create_contract_with_model()
    contract_year = domainfactory.contract_year(contract)

    invoice = create_invoice_with_contract_position(contract_year)
    invoice_position = next(iter(invoice.positions))
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    export_dto = map_contract_to_export_dto(contract_model)
    rows = flatten_contract_data(export_dto)

    assert len(rows) == 1
    row = rows[0]

    assert row["contract_name"] == str(contract.name)
    assert row["start_date"] == str(contract.period.start)
    assert row["end_date"] == str(contract.period.end)
    assert row["publishers"] == "Test Publisher"
    assert row["journals"] == "Test Journal"
    assert row["publication_billing"] == str(contract.publication_billing)
    assert row["active_status"] == str(contract.is_active())

    assert row["invoice_number"] == invoice.number
    assert row["invoice_date"] == invoice.date.isoformat()
    assert row["creditor"] == invoice_model.creditor.name
    assert row["invoice_status"] == invoice.status.value
    assert row["invoice_currency"] == invoice.currency().code
    assert row["invoice_comment"] == invoice.comment or ""
    assert row["external_invoice_id"] == invoice.external_invoice_id or ""

    assert Decimal(row["position_amount"]) == invoice_position.cost.amount
    assert Decimal(row["tax_rate"]) == invoice_position.tax_rate * 100
    assert row["cost_type"] == invoice_position.item.cost_type.value
    assert row["contract_year"] == str(contract_year.year)


@pytest.mark.django_db
def test__contract_with_invoice_position_with_funding_assignments__flatten_to_csv__creates_multiple_rows() -> (
    None
):
    contract, contract_model = _create_contract_with_model()
    contract_year = domainfactory.contract_year(contract)

    from coda.domain.finance import invoice_positions

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

    export_dto = map_contract_to_export_dto(contract_model)
    rows = flatten_contract_data(export_dto)

    assert len(rows) == 3
    assert rows[0]["contract_name"] == str(contract.name)

    funded_amounts = sorted(Decimal(row["funded_amount"]) for row in rows)
    funding_sources = sorted(row["funding_source_name"] for row in rows)
    assert funded_amounts == [Decimal("800.00"), Decimal("1000.00"), Decimal("1200.00")]
    assert funding_sources == ["Budget A", "Budget B", "Budget C"]


@pytest.mark.django_db
def test__contract_with_multiple_invoices__flatten_to_csv__combines_all_rows() -> None:
    contract, contract_model = _create_contract_with_model()
    contract_year = domainfactory.contract_year(contract)

    position1 = domainfactory.contract_position(contract_year)
    creditor = modelfactory.creditor()
    invoice1 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position1])
    invoice_service.save(invoice1)

    position2 = domainfactory.contract_position(contract_year)
    budget_x = modelfactory.budget(name="Budget X")
    budget_y = modelfactory.budget(name="Budget Y")
    position2.assign_funding(
        Budget(FundingSourceId(budget_x.pk), budget_x.name), position2.cost.amount * Decimal("0.6")
    )
    position2.assign_remaining(Budget(FundingSourceId(budget_y.pk), budget_y.name))

    invoice2 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position2])
    invoice_service.save(invoice2)

    export_dto = map_contract_to_export_dto(contract_model)
    rows = flatten_contract_data(export_dto)

    assert len(rows) == 3

    invoice_numbers = [row["invoice_number"] for row in rows]
    assert invoice_numbers.count(invoice1.number) == 1
    assert invoice_numbers.count(invoice2.number) == 2
