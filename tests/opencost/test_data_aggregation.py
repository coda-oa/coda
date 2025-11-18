from datetime import date
import pytest

from tests import modelfactory
from coda.apps.opencost.data_aggregation import get_publications_for_period
from coda.apps.invoices.models import Invoice, Position, Creditor
from decimal import Decimal


@pytest.mark.django_db
def test__publications_of_different_dates__querying_specific_time_range__only_returns_publications_in_range() -> (
    None
):
    publication_before_period = modelfactory.publication(title="Before Period")
    publication_before_period.online_publication_date = date(2023, 1, 15)
    publication_before_period.save()

    publication_in_period_1 = modelfactory.publication(title="In Period 1")
    publication_in_period_1.online_publication_date = date(2023, 2, 10)
    publication_in_period_1.save()

    publication_in_period_2 = modelfactory.publication(title="In Period 2")
    publication_in_period_2.online_publication_date = date(2023, 2, 20)
    publication_in_period_2.save()

    publication_after_period = modelfactory.publication(title="After Period")
    publication_after_period.online_publication_date = date(2023, 3, 5)
    publication_after_period.save()

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
    publication.online_publication_date = date(2024, 6, 15)
    publication.save()

    creditor = Creditor.objects.create(name="Creditor Name")
    invoice = Invoice.objects.create(
        creditor=creditor, date=date(2024, 6, 1), number="12345", status="paid"
    )

    Position.objects.create(
        invoice=invoice,
        publication=publication,
        description="APC for test article",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="APC",
        tax_rate=Decimal("0.19"),
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
