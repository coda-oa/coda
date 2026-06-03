import pytest
from datetime import date
from decimal import Decimal
from io import StringIO

import polars as pl

# from coda.apps.checklist import repository
from coda.apps.exports.services.fundingrequest_csv.export_service import (
    export_fundingrequests_to_csv,
)
from coda.apps.invoices.models import FundingAssignment, Position
from tests import modelfactory
from coda.domain.fundingrequest.review import ReviewResult, Review
from coda.domain.money import Money, Currency
from coda.domain.fundingrequest import FundingRequestId
from coda.apps.fundingrequests.repository import save_review


@pytest.mark.django_db
def test__single_funding_request_with_one_invoice__export_to_csv__returns_csv_with_one_row() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication for Export")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

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
        tax_rate=Decimal("0.19"),
        external_position_id="POS-001",
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    assert isinstance(requests_exports, str)
    assert requests_exports
    assert ";" in requests_exports.splitlines()[0]

    df = pl.read_csv(StringIO(requests_exports), separator=";")

    assert df.height == 1
    assert df["publication_title"][0] == "Test Publication for Export"
    assert df["invoice_number"][0] == "INV-001"
    assert df["invoice_date"][0] == "2026-05-01"


@pytest.mark.django_db
def test__funding_request_without_invoices__export_to_csv__returns_one_row_with_empty_cost_fields() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Publication Only")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1

    assert df["publication_title"][0] == "Publication Only"
    assert df["invoice_number"][0] == ""
    assert df["invoice_date"][0] == ""
    assert df["position_amount"][0] == ""
    assert df["funded_amount"][0] == ""


@pytest.mark.django_db
def test__no_funding_requests_in_period__export_to_csv__returns_csv_with_only_header() -> None:
    funding_request_not_in_period = modelfactory.fundingrequest(title="Test Publication for Export")
    funding_request_not_in_period.request_date = date(2025, 5, 1)
    funding_request_not_in_period.save()

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    assert isinstance(requests_exports, str)
    assert requests_exports
    assert ";" in requests_exports.splitlines()[0]

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 0


@pytest.mark.django_db
def test__funding_request_with_invoice_position_with_multiple_funding_assignments__export_to_csv__creates_multiple_rows() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Split Cost Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    invoice = modelfactory.invoice()
    invoice.number = "INV-002"
    invoice.date = date(2026, 5, 1)
    invoice.save()

    position = Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-002",
    )

    FundingAssignment.objects.create(
        position=position,
        funding_source=modelfactory.budget(name="Budget 1"),
        amount=Decimal("1200.00"),
    )

    FundingAssignment.objects.create(
        position=position,
        funding_source=modelfactory.budget(name="Budget 2"),
        amount=Decimal("800.00"),
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 2

    assert df["publication_title"][0] == "Split Cost Publication"
    assert df["invoice_number"][0] == "INV-002"
    assert Decimal(df["funded_amount"][0]) == Decimal("1200.00")
    assert df["funding_source_name"][0] == "Budget 1"

    assert df["publication_title"][1] == "Split Cost Publication"
    assert df["invoice_number"][1] == "INV-002"
    assert Decimal(df["funded_amount"][1]) == Decimal("800.00")
    assert df["funding_source_name"][1] == "Budget 2"


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__export_to_csv__creates_multiple_rows() -> None:
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Multi-Invoice Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    invoice1 = modelfactory.invoice()
    invoice1.number = "INV-003"
    invoice1.date = date(2026, 5, 1)
    invoice1.save()

    Position.objects.create(
        invoice=invoice1,
        publication=funding_request.publication,
        description="First invoice charge",
        cost_amount=Decimal("1000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-003",
    )

    invoice2 = modelfactory.invoice()
    invoice2.number = "INV-004"
    invoice2.date = date(2026, 5, 10)
    invoice2.save()

    Position.objects.create(
        invoice=invoice2,
        publication=funding_request.publication,
        description="Second invoice charge",
        cost_amount=Decimal("500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-004",
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 2

    assert df["publication_title"][0] == "Multi-Invoice Publication"
    assert df["invoice_number"][0] == "INV-003"

    assert df["publication_title"][1] == "Multi-Invoice Publication"
    assert df["invoice_number"][1] == "INV-004"


@pytest.mark.django_db
def test__funding_request_with_review_result__export_to_csv__includes_review_results_and_labels() -> (
    None
):
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Reviewed Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    invoice = modelfactory.invoice()
    invoice.number = "INV-005"
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
        external_position_id="POS-005",
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(period_start, period_end)

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1

    assert df["publication_title"][0] == "Reviewed Publication"
    assert df["review_result"][0] == "approved"


@pytest.mark.django_db
def test__funding_request_with_invoice_filters__export_to_csv__returns_filtered_results() -> None:
    # ARRANGE
    funding_request = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    invoice = modelfactory.invoice()
    invoice.number = "INV-006"
    invoice.date = date(2026, 5, 1)
    invoice.creditor = modelfactory.creditor(name="Test Creditor")
    invoice.status = "paid"
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-006",
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(
        period_start,
        period_end,
        invoice_status="paid",
        invoice_creditor="Test Creditor",
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1

    assert df["publication_title"][0] == "Filtered Publication"
    assert df["invoice_number"][0] == "INV-006"
    assert df["creditor"][0] == "Test Creditor"
    assert df["invoice_status"][0] == "paid"


@pytest.mark.django_db
def test__funding_request_with_combined_filters__export_to_csv__returns_correctly_filtered_results() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()

    save_review(
        Review(FundingRequestId(funding_request.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    invoice = modelfactory.invoice()
    invoice.number = "INV-006"
    invoice.date = date(2026, 5, 1)
    invoice.creditor = modelfactory.creditor(name="Test Creditor")
    invoice.status = "paid"
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-006",
    )

    funding_request_rejected = modelfactory.fundingrequest(title="Filtered Publication")
    funding_request_rejected.request_date = date(2026, 5, 1)
    funding_request_rejected.save()

    save_review(
        Review(FundingRequestId(funding_request_rejected.id)).update_review(
            ReviewResult.Rejected, Money(Decimal("2000.00"), Currency.EUR)
        )
    )

    invoice = modelfactory.invoice()
    invoice.number = "INV-006"
    invoice.date = date(2026, 5, 1)
    invoice.creditor = modelfactory.creditor(name="Test Creditor")
    invoice.status = "paid"
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request_rejected.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-006",
    )

    period_start = date(2026, 1, 1)
    period_end = date(2026, 12, 31)
    requests_exports = export_fundingrequests_to_csv(
        period_start,
        period_end,
        invoice_status="paid",
        invoice_creditor="Test Creditor",
        review_results=[ReviewResult.Approved],
    )

    df = pl.read_csv(StringIO(requests_exports), separator=";")
    assert df.height == 1
    assert df["publication_title"][0] == "Filtered Publication"
    assert df["review_result"][0] == "approved"
    assert df["invoice_status"][0] == "paid"
    assert df["creditor"][0] == "Test Creditor"
