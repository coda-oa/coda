from datetime import date
import pytest

from tests import modelfactory
from coda.apps.opencost.data_aggregation import get_invoices_for_period, get_publications_for_period
from tests.opencost.helpers import create_creditor, create_publication_with_invoice, create_invoice
from decimal import Decimal


@pytest.mark.django_db
def test__publications_of_different_dates__querying_specific_time_range__only_returns_publications_in_range() -> (
    None
):
    publication_before_period = modelfactory.publication(title="Before Period")
    publication_in_period_1 = modelfactory.publication(title="In Period 1")
    publication_in_period_2 = modelfactory.publication(title="In Period 2")
    publication_after_period = modelfactory.publication(title="After Period")

    create_publication_with_invoice(
        publication_before_period,
        invoice_date=date(2023, 1, 20),
        invoice_number="INV-BEFORE",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_in_period_1,
        invoice_date=date(2023, 2, 10),
        invoice_number="INV-1",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_in_period_2,
        invoice_date=date(2023, 2, 25),
        invoice_number="INV-2",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_after_period,
        invoice_date=date(2023, 3, 10),
        invoice_number="INV-AFTER",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )

    query_results = get_publications_for_period(
        start_date=date(2023, 2, 1),
        end_date=date(2023, 2, 28),
    )

    assert publication_in_period_1 in query_results
    assert publication_in_period_2 in query_results
    assert publication_before_period not in query_results
    assert publication_after_period not in query_results


@pytest.mark.django_db
def test__publication_with_invoice__querying_data__invoice_data_is_available() -> None:
    publication = modelfactory.publication(title="Publication with Invoice")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="12345",
        creditor_name="Creditor Name",
        cost_amount=Decimal("1500.00"),
        cost_type="APC",
    )

    results = get_publications_for_period(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
    )

    assert publication in results

    pub = results.first()
    assert pub is not None
    positions = list(pub.position_set.all())
    assert len(positions) == 1
    assert positions[0].invoice.number == "12345"
    assert positions[0].invoice.creditor.name == "Creditor Name"
    assert positions[0].cost_amount == Decimal("1500.00")


@pytest.mark.django_db
def test__invoices_with_different_dates__querying_specific_time_range__only_returns_invoices_in_range() -> (
    None
):
    creditor_a = create_creditor(name="Creditor A")
    invoice_before_period = create_invoice(
        creditor=creditor_a,
        invoice_date=date(2023, 1, 15),
        number="INV-001",
    )

    creditor_b = create_creditor(name="Creditor B")
    invoice_in_period_1 = create_invoice(
        creditor=creditor_b,
        invoice_date=date(2023, 2, 10),
        number="INV-002",
    )

    creditor_c = create_creditor(name="Creditor C")
    invoice_in_period_2 = create_invoice(
        creditor=creditor_c,
        invoice_date=date(2023, 2, 20),
        number="INV-003",
    )

    creditor_d = create_creditor(name="Creditor D")
    invoice_after_period = create_invoice(
        creditor=creditor_d,
        invoice_date=date(2023, 3, 5),
        number="INV-004",
    )

    query_results = get_invoices_for_period(
        start_date=date(2023, 2, 1),
        end_date=date(2023, 2, 28),
    )

    assert invoice_in_period_1 in query_results
    assert invoice_in_period_2 in query_results
    assert invoice_before_period not in query_results
    assert invoice_after_period not in query_results


@pytest.mark.django_db
def test__paid_and_unpaid_invoices__querying_invoices_for_period__returns_only_paid_invoices() -> (
    None
):
    creditor = create_creditor(name="Creditor E")
    paid_invoice = create_invoice(
        creditor=creditor,
        invoice_date=date(2024, 5, 15),
        number="INV-PAID",
        status="paid",
    )
    unpaid_invoice = create_invoice(
        creditor=creditor,
        invoice_date=date(2024, 5, 20),
        number="INV-UNPAID",
        status="unpaid",
    )

    query_results = get_invoices_for_period(
        start_date=date(2024, 5, 1),
        end_date=date(2024, 5, 31),
    )

    assert paid_invoice in query_results
    assert unpaid_invoice not in query_results
