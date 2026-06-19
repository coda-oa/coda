# tests/exports/fundingrequest_csv/test_flatteners.py

import pytest
from decimal import Decimal
from datetime import date

from coda.apps.exports.services.fundingrequest_csv.flatteners import flatten_detailed
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.apps.invoices.models import Position, FundingAssignment
from tests import modelfactory


def assert_all_rows_have_same_value(
    rows: list[dict[str, str]], field: str, expected_value: str
) -> None:
    actual_values = [row[field] for row in rows]
    assert actual_values == [expected_value] * len(
        rows
    ), f"Expected all rows to have {field}={expected_value}, but got: {actual_values}"


def assert_all_rows_have_same_decimal_value(
    rows: list[dict[str, str]], field: str, expected_value: Decimal
) -> None:
    actual_values = [Decimal(row[field]) for row in rows]
    assert actual_values == [expected_value] * len(
        rows
    ), f"Expected all rows to have {field}={expected_value}, but got: {actual_values}"


@pytest.mark.django_db
def test__funding_request_with_single_invoice_position_without_split__flatten_to_csv__creates_one_csv_row() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication for Export")

    invoice = modelfactory.invoice()
    invoice.number = "INV-001"
    invoice.date = date(2026, 5, 1)
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-001",
    )

    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 1
    row = rows[0]
    assert row["publication_title"] == "Test Publication for Export"
    assert row["invoice_number"] == "INV-001"
    assert Decimal(row["position_amount"]) == Decimal("1500.00")


@pytest.mark.django_db
def test__funding_request_with_invoice_position_with_funding_assignments__flatten_to_csv__creates_multiple_rows() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Split Cost Publication")

    invoice = modelfactory.invoice()
    invoice.number = "INV-002"
    invoice.date = date(2026, 5, 10)
    invoice.save()

    position = Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge with split",
        cost_amount=Decimal("3000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-002",
    )

    budget_a = modelfactory.budget(name="Budget A")
    budget_b = modelfactory.budget(name="Budget B")
    budget_c = modelfactory.budget(name="Budget C")

    FundingAssignment.objects.create(
        position=position,
        funding_source=budget_a,
        amount=Decimal("1000.00"),
    )
    FundingAssignment.objects.create(
        position=position,
        funding_source=budget_b,
        amount=Decimal("1200.00"),
    )
    FundingAssignment.objects.create(
        position=position,
        funding_source=budget_c,
        amount=Decimal("800.00"),
    )

    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 3
    assert_all_rows_have_same_value(rows, "publication_title", "Split Cost Publication")
    assert_all_rows_have_same_value(rows, "invoice_number", "INV-002")
    assert_all_rows_have_same_decimal_value(rows, "position_amount", Decimal("3000.00"))

    funded_amounts = [Decimal(row["funded_amount"]) for row in rows]
    funding_sources = [row["funding_source_name"] for row in rows]
    assert sorted(funded_amounts) == [Decimal("800.00"), Decimal("1000.00"), Decimal("1200.00")]
    assert sorted(funding_sources) == ["Budget A", "Budget B", "Budget C"]


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__flatten_to_csv__combines_all_rows() -> None:
    funding_request = modelfactory.fundingrequest(title="Multi-Invoice Publication")

    invoice1 = modelfactory.invoice()
    invoice1.number = "INV-003"
    invoice1.date = date(2026, 5, 15)
    invoice1.save()

    Position.objects.create(
        invoice=invoice1,
        publication=funding_request.publication,
        description="First invoice position",
        cost_amount=Decimal("1000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )

    invoice2 = modelfactory.invoice()
    invoice2.number = "INV-004"
    invoice2.date = date(2026, 5, 20)
    invoice2.save()

    position2 = Position.objects.create(
        invoice=invoice2,
        publication=funding_request.publication,
        description="Second invoice position",
        cost_amount=Decimal("500.00"),
        cost_currency="EUR",
        cost_type="hybrid-oa",
        tax_rate=Decimal("0.19"),
    )

    budget_x = modelfactory.budget(name="Budget X")
    budget_y = modelfactory.budget(name="Budget Y")

    FundingAssignment.objects.create(
        position=position2,
        funding_source=budget_x,
        amount=Decimal("300.00"),
    )
    FundingAssignment.objects.create(
        position=position2,
        funding_source=budget_y,
        amount=Decimal("200.00"),
    )
    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 3

    assert_all_rows_have_same_value(rows, "publication_title", "Multi-Invoice Publication")

    invoice_numbers = [row["invoice_number"] for row in rows]
    assert invoice_numbers.count("INV-003") == 1
    assert invoice_numbers.count("INV-004") == 2


@pytest.mark.django_db
def test__missing_optional_fields__flatten_to_csv__handles_none_values() -> None:
    funding_request = modelfactory.fundingrequest(title="Minimal Publication")

    funding_request.labels.clear()
    funding_request.external_funding.all().delete()

    invoice = modelfactory.invoice()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Minimal position",
        cost_amount=Decimal("100.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.00"),
        external_position_id="",
    )

    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 1

    row = rows[0]

    assert row["labels"] == ""
    assert row["project_id"] == ""
    assert row["project_name"] == ""
    assert row["funding_organization"] == ""
    assert row["funding_source_name"] == ""
    assert row["funding_source_type"] == ""

    assert row["publication_title"] == "Minimal Publication"
    assert Decimal(row["position_amount"]) == Decimal("100.00")
