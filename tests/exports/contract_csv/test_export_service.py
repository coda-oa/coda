from decimal import Decimal
from io import StringIO

import polars as pl

import pytest

from coda.apps.exports.services.contract_csv.export_service import export_contract_to_csv
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.domain.finance.invoice import CreditorId, PaymentStatus
from coda.contexts.finance.services import invoice_service
from tests import domainfactory, modelfactory
from tests.exports.helpers import (
    create_contract_and_year,
    create_invoice_with_contract_position,
    create_invoice_with_funded_position,
    create_invoices_with_positions,
)


@pytest.mark.django_db
def test__contract_with_one_invoice_position_and_no_funding_assignments__export_to_csv__returns_csv_with_one_row() -> (
    None
):
    contract, _, contract_year = create_contract_and_year()

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
    contract, _, contract_year = create_contract_and_year()

    create_invoice_with_funded_position(contract_year)

    export = export_contract_to_csv(InvoiceSearchParams())

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 3

    funded_amounts = sorted(df["funded_amount"].to_list())
    funding_sources = sorted(df["funding_source_name"].to_list())
    assert funded_amounts == [800.0, 1000.0, 1200.0]
    assert funding_sources == ["Budget A", "Budget B", "Budget C"]


@pytest.mark.django_db
def test__contract_with_multiple_invoices__export_to_csv__combines_all_rows() -> None:
    contract, _, contract_year = create_contract_and_year()

    invoice1, invoice2 = create_invoices_with_positions(contract_year)

    export = export_contract_to_csv(InvoiceSearchParams())

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 3
    invoice_numbers = df["invoice_number"].to_list()
    assert invoice_numbers.count(invoice1.number) == 1
    assert invoice_numbers.count(invoice2.number) == 2


@pytest.mark.django_db
def test__contract_with_mixed_paid_and_unpaid_invoices__export_with_paid_filter__includes_only_paid_invoice_data() -> (
    None
):
    contract, _, contract_year = create_contract_and_year()

    paid_position = domainfactory.contract_position(contract_year)
    creditor = modelfactory.creditor()
    paid_invoice = domainfactory.invoice(
        creditor=CreditorId(creditor.pk), positions=[paid_position]
    )
    paid_invoice.pay()
    paid_invoice.id = invoice_service.save(paid_invoice)

    unpaid_position = domainfactory.contract_position(contract_year)
    unpaid_invoice = domainfactory.invoice(
        creditor=CreditorId(creditor.pk), positions=[unpaid_position]
    )
    unpaid_invoice.reset_payment()
    unpaid_invoice.id = invoice_service.save(unpaid_invoice)

    export = export_contract_to_csv(InvoiceSearchParams(payment_status=PaymentStatus.Paid))

    df = pl.read_csv(StringIO(export), separator=";")

    assert df.height == 1
    assert df["invoice_number"][0] == paid_invoice.number
