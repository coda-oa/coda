from decimal import Decimal
from io import StringIO

import polars as pl

import pytest

from coda.apps.exports.services.contract_csv.export_service import export_contract_to_csv
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.finance.invoice_positions import ContractItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.contexts.finance.services import invoice_service
from tests import domainfactory, modelfactory
from tests.exports.helpers import create_contract_with_model, create_invoice_with_contract_position


@pytest.mark.django_db
def test__contract_with_one_invoice_position_and_no_funding_assignments__export_to_csv__returns_csv_with_one_row() -> (
    None
):
    contract, _ = create_contract_with_model()
    contract_year = domainfactory.contract_year(contract)

    invoice = create_invoice_with_contract_position(contract_year)
    invoice_position = next(iter(invoice.positions))

    export = export_contract_to_csv(InvoiceSearchParams())

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 1
    assert df["contract_name"][0] == str(contract.name)
    assert df["start_date"][0] == str(contract.period.start)
    assert df["end_date"][0] == str(contract.period.end)
    assert df["invoice_number"][0] == invoice.number
    assert df["invoice_date"][0] == invoice.date.isoformat()
    assert Decimal(str(df["position_amount"][0])) == invoice_position.cost.amount


@pytest.mark.django_db
def test__contract_with_invoice_position_with_funding_assignments__export_to_csv__creates_multiple_rows() -> (
    None
):
    contract, _ = create_contract_with_model()
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

    export = export_contract_to_csv(InvoiceSearchParams())

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 3

    funded_amounts = sorted(Decimal(str(v)) for v in df["funded_amount"].to_list())
    funding_sources = sorted(df["funding_source_name"].to_list())
    assert funded_amounts == [Decimal("800.00"), Decimal("1000.00"), Decimal("1200.00")]
    assert funding_sources == ["Budget A", "Budget B", "Budget C"]


@pytest.mark.django_db
def test__contract_with_multiple_invoices__export_to_csv__combines_all_rows() -> None:
    contract, _ = create_contract_with_model()
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

    export = export_contract_to_csv(InvoiceSearchParams())

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 3
    invoice_numbers = df["invoice_number"].to_list()
    assert invoice_numbers.count(invoice1.number) == 1
    assert invoice_numbers.count(invoice2.number) == 2
