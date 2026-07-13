# tests/exports/fundingrequest_csv/test_flatteners.py

import pytest
from decimal import Decimal
from datetime import date

from coda.apps.exports.services.fundingrequest_csv.flatteners import flatten_detailed
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services import invoice_service
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId
from tests import modelfactory
from tests.exports.fundingrequest_csv.helpers import (
    create_funding_request,
    create_invoice_with_publication_position,
)


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
    funding_request = create_funding_request(title="Test Publication for Export")
    invoice = create_invoice_with_publication_position(funding_request)
    invoice_position = list(invoice.positions)[0]

    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 1
    row = rows[0]
    assert row["publication_title"] == "Test Publication for Export"
    assert row["invoice_number"] == invoice.number
    assert Decimal(row["position_amount"]) == invoice_position.cost.amount


@pytest.mark.django_db
def test__funding_request_with_invoice_position_with_funding_assignments__flatten_to_csv__creates_multiple_rows() -> (
    None
):
    funding_request = create_funding_request(title="Split Cost Publication")

    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("3000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id="POS-002",
    )

    invoice = Invoice.new(
        number="INV-002",
        date=date(2026, 5, 10),
        creditor=creditor_id,
        positions=[position],
    )

    budget_a = Budget(None, "Budget A")
    budget_a.id = funding_source_repository.create(budget_a)
    budget_b = Budget(None, "Budget B")
    budget_b.id = funding_source_repository.create(budget_b)
    budget_c = Budget(None, "Budget C")
    budget_c.id = funding_source_repository.create(budget_c)

    position.assign_funding(budget_a, Decimal("1000.00"))
    position.assign_funding(budget_b, Decimal("1200.00"))
    position.assign_funding(budget_c, Decimal("800.00"))

    invoice.id = invoice_service.save(invoice)

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
    funding_request = create_funding_request(title="Multi-Invoice Publication")

    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)

    position1 = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("1000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )

    invoice1 = Invoice.new(
        number="INV-003",
        date=date(2026, 5, 15),
        creditor=creditor_id,
        positions=[position1],
    )
    invoice1.id = invoice_service.save(invoice1)

    position2 = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("hybrid-oa"),
        ),
        cost=Money(Decimal("500.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
    )

    invoice2 = Invoice.new(
        number="INV-004",
        date=date(2026, 5, 20),
        creditor=creditor_id,
        positions=[position2],
    )

    budget_x = Budget(None, "Budget X")
    budget_x.id = funding_source_repository.create(budget_x)
    budget_y = Budget(None, "Budget Y")
    budget_y.id = funding_source_repository.create(budget_y)

    position2.assign_funding(budget_x, Decimal("300.00"))
    position2.assign_funding(budget_y, Decimal("200.00"))

    invoice2.id = invoice_service.save(invoice2)

    export_dto = map_funding_request_to_export_dto(funding_request)
    rows = flatten_detailed(export_dto)

    assert len(rows) == 3
    assert_all_rows_have_same_value(rows, "publication_title", "Multi-Invoice Publication")

    invoice_numbers = [row["invoice_number"] for row in rows]
    assert invoice_numbers.count("INV-003") == 1
    assert invoice_numbers.count("INV-004") == 2


@pytest.mark.django_db
def test__missing_optional_fields__flatten_to_csv__handles_none_values() -> None:
    funding_request = create_funding_request(title="Minimal Publication")

    funding_request.labels.clear()
    funding_request.external_funding.all().delete()

    invoice = create_invoice_with_publication_position(funding_request)
    invoice_position = list(invoice.positions)[0]

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
    assert Decimal(row["position_amount"]) == invoice_position.cost.amount
