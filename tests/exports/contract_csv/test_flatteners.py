from decimal import Decimal

import pytest
from coda.apps.exports.services.contract_csv.flatteners import flatten_contract_data
from coda.apps.exports.services.contract_csv.mappers import map_contract_to_export_dto
from coda.apps.invoices.models import Invoice as InvoiceModel
from tests.exports.helpers import (
    create_contract_and_year,
    create_invoice_with_contract_position,
    create_invoice_with_funded_position,
    create_invoices_with_positions,
)


@pytest.mark.django_db
def test__contract_with_single_invoice_position_without_split__flatten_to_csv__creates_one_csv_row() -> (
    None
):
    contract, contract_model, contract_year = create_contract_and_year()

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
    contract, contract_model, contract_year = create_contract_and_year()

    create_invoice_with_funded_position(contract_year)

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
    contract, contract_model, contract_year = create_contract_and_year()

    invoice1, invoice2 = create_invoices_with_positions(contract_year)

    export_dto = map_contract_to_export_dto(contract_model)
    rows = flatten_contract_data(export_dto)

    assert len(rows) == 3

    invoice_numbers = [row["invoice_number"] for row in rows]
    assert invoice_numbers.count(invoice1.number) == 1
    assert invoice_numbers.count(invoice2.number) == 2
