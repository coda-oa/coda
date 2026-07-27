# tests/exports/fundingrequest_csv/test_flatteners.py

import pytest
from decimal import Decimal

from coda.apps.exports.services.fundingrequest_csv.flatteners import flatten_detailed
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.contexts.finance.services import invoice_service
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory
from tests.exports.helpers import (
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
    invoice_position = next(iter(invoice.positions))

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

    position = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(Decimal("3000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id="POS-002",
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

    export_dto = map_funding_request_to_export_dto(funding_request)

    rows = flatten_detailed(export_dto)

    assert len(rows) == 3
    assert_all_rows_have_same_value(rows, "publication_title", "Split Cost Publication")
    assert_all_rows_have_same_value(rows, "invoice_number", invoice.number)
    assert_all_rows_have_same_decimal_value(rows, "position_amount", Decimal("3000.00"))

    funded_amounts = sorted(Decimal(row["funded_amount"]) for row in rows)
    funding_sources = sorted(row["funding_source_name"] for row in rows)
    assert funded_amounts == [Decimal("800.00"), Decimal("1000.00"), Decimal("1200.00")]
    assert funding_sources == ["Budget A", "Budget B", "Budget C"]


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__flatten_to_csv__combines_all_rows() -> None:
    funding_request = create_funding_request(title="Multi-Invoice Publication")

    creditor = modelfactory.creditor()
    position1 = domainfactory.publication_position(PublicationId(funding_request.publication.id))
    invoice1 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position1])
    invoice_service.save(invoice1)

    position2 = domainfactory.publication_position(PublicationId(funding_request.publication.id))

    budget_x = modelfactory.budget(name="Budget X")
    budget_y = modelfactory.budget(name="Budget Y")
    position2.assign_funding(
        Budget(FundingSourceId(budget_x.pk), budget_x.name), position2.cost.amount * Decimal("0.6")
    )
    position2.assign_remaining(Budget(FundingSourceId(budget_y.pk), budget_y.name))

    invoice2 = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position2])
    invoice_service.save(invoice2)

    export_dto = map_funding_request_to_export_dto(funding_request)
    rows = flatten_detailed(export_dto)

    assert len(rows) == 3
    assert_all_rows_have_same_value(rows, "publication_title", "Multi-Invoice Publication")

    invoice_numbers = [row["invoice_number"] for row in rows]
    assert invoice_numbers.count(invoice1.number) == 1
    assert invoice_numbers.count(invoice2.number) == 2


@pytest.mark.django_db
def test__missing_optional_fields__flatten_to_csv__handles_none_values() -> None:
    funding_request = create_funding_request(title="Minimal Publication")

    funding_request.labels.clear()
    funding_request.external_funding.all().delete()

    invoice = create_invoice_with_publication_position(funding_request)
    invoice_position = next(iter(invoice.positions))

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
