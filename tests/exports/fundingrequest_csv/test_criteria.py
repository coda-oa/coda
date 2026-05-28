import pytest
from datetime import date
from decimal import Decimal

from tests import modelfactory
from coda.apps.invoices.models import FundingAssignment, Position

from coda.apps.exports.services.fundingrequest_csv.criteria import (
    InvoiceDateRangeCriteria,
    InvoicePaymentStatusCriteria,
    InvoiceCreditorCriteria,
    InvoiceFundingSourceCriteria,
)
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchCriteria
from coda.domain.finance.invoice import FundingSourceId


@pytest.mark.django_db
def test__funding_request_invoice_dates_in_and_not_in_range__filtered_by_invoice_date__returns_only_funding_requests_with_invoices_in_range() -> (
    None
):

    fr_in_range = modelfactory.fundingrequest(title="In Range Invoice")
    invoice_in_range = modelfactory.invoice()
    invoice_in_range.date = date(2026, 3, 15)  # March - IN RANGE
    invoice_in_range.save()

    Position.objects.create(
        invoice=invoice_in_range,
        publication=fr_in_range.publication,
        description="In range position",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-RANGE",
    )

    fr_not_in_range = modelfactory.fundingrequest(title="Not in Range Invoice")
    invoice_not_in_range = modelfactory.invoice()
    invoice_not_in_range.date = date(2026, 6, 15)
    invoice_not_in_range.save()

    Position.objects.create(
        invoice=invoice_not_in_range,
        publication=fr_not_in_range.publication,
        description="Not in range position",
        cost_amount=Decimal("3000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-NOT-IN-RANGE",
    )

    criteria = InvoiceDateRangeCriteria(
        invoice_start=date(2026, 3, 1),
        invoice_end=date(2026, 5, 31),
    )
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_in_range]


@pytest.mark.django_db
def test__funding_request_with_invoice__filtered_by_invoice_payment_status__returns_only_funding_requests_with_invoices_matching_status() -> (
    None
):

    # Arrange: Create funding requests with invoices of different payment statuses
    fr_paid = modelfactory.fundingrequest(title="Paid Invoice")
    invoice_paid = modelfactory.invoice()
    invoice_paid.status = "paid"
    invoice_paid.save()
    Position.objects.create(
        invoice=invoice_paid,
        publication=fr_paid.publication,
        description="Paid position",
        cost_amount=Decimal("2500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-PAID",
    )

    fr_unpaid = modelfactory.fundingrequest(title="Unpaid Invoice")
    invoice_unpaid = modelfactory.invoice()
    invoice_unpaid.status = "unpaid"
    invoice_unpaid.save()
    Position.objects.create(
        invoice=invoice_unpaid,
        publication=fr_unpaid.publication,
        description="Unpaid position",
        cost_amount=Decimal("3000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-UNPAID",
    )

    criteria = InvoicePaymentStatusCriteria(payment_status="paid")
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_paid]


@pytest.mark.django_db
def test__funding_request_with_invoice__filtered_by_invoice_creditor__returns_only_funding_requests_with_invoices_matching_creditor() -> (
    None
):
    fr_creditor_a = modelfactory.fundingrequest(title="Creditor A Invoice")
    creditor_a = modelfactory.creditor(name="Creditor A")
    invoice_a = modelfactory.invoice()
    invoice_a.creditor = creditor_a
    invoice_a.save()

    Position.objects.create(
        invoice=invoice_a,
        publication=fr_creditor_a.publication,
        description="Creditor A position",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-CREDITOR-A",
    )
    fr_creditor_b = modelfactory.fundingrequest(title="Creditor B Invoice")
    creditor_b = modelfactory.creditor(name="Creditor B")
    invoice_b = modelfactory.invoice()
    invoice_b.creditor = creditor_b
    invoice_b.save()
    Position.objects.create(
        invoice=invoice_b,
        publication=fr_creditor_b.publication,
        description="Creditor B position",
        cost_amount=Decimal("1800.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-CREDITOR-B",
    )

    criteria = InvoiceCreditorCriteria(creditor_name="Creditor A")
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_creditor_a]


@pytest.mark.django_db
def test__funding_request_with_invoice__filtered_by_funding_source__returns_only_funding_requests_with_invoices_matching_funding_source() -> (
    None
):
    fr_funding_source_a = modelfactory.fundingrequest(title="Funding Source A Invoice")
    invoice_a = modelfactory.invoice()
    invoice_a.save()

    position_a = Position.objects.create(
        invoice=invoice_a,
        publication=fr_funding_source_a.publication,
        description="Funding Source A position",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-FUNDING-SOURCE-A",
    )

    budget_a = modelfactory.budget(name="Funding Source A")
    FundingAssignment.objects.create(
        position=position_a,
        funding_source=budget_a,
        amount=Decimal("1500.00"),
    )

    fr_funding_source_b = modelfactory.fundingrequest(title="Funding Source B Invoice")
    invoice_b = modelfactory.invoice()
    invoice_b.save()

    position_b = Position.objects.create(
        invoice=invoice_b,
        publication=fr_funding_source_b.publication,
        description="Funding Source B position",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-FUNDING-SOURCE-B",
    )

    budget_b = modelfactory.budget(name="Funding Source B")
    FundingAssignment.objects.create(
        position=position_b,
        funding_source=budget_b,
        amount=Decimal("2000.00"),
    )

    criteria = InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_a.pk))
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_funding_source_a]


@pytest.mark.django_db
def test__combining_multiple_criteria__filters_funding_requests_correctly() -> None:
    fr1 = modelfactory.fundingrequest(title="FR 1")
    invoice1 = modelfactory.invoice()
    invoice1.date = date(2026, 4, 10)
    invoice1.status = "paid"
    creditor1 = modelfactory.creditor(name="Creditor X")
    invoice1.creditor = creditor1
    invoice1.save()
    Position.objects.create(
        invoice=invoice1,
        publication=fr1.publication,
        description="Position 1",
        cost_amount=Decimal("1000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-1",
    )
    budget_x = modelfactory.budget(name="Budget X")
    FundingAssignment.objects.create(
        position=Position.objects.get(external_position_id="POS-1"),
        funding_source=budget_x,
        amount=Decimal("1000.00"),
    )

    fr2 = modelfactory.fundingrequest(title="FR 2")
    invoice2 = modelfactory.invoice()
    invoice2.date = date(2026, 5, 20)
    invoice2.status = "unpaid"
    creditor2 = modelfactory.creditor(name="Creditor Y")
    invoice2.creditor = creditor2
    invoice2.save()
    Position.objects.create(
        invoice=invoice2,
        publication=fr2.publication,
        description="Position 2",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-2",
    )
    budget_y = modelfactory.budget(name="Budget Y")
    FundingAssignment.objects.create(
        position=Position.objects.get(external_position_id="POS-2"),
        funding_source=budget_y,
        amount=Decimal("2000.00"),
    )

    criteria: list[FundingRequestSearchCriteria] = [
        InvoiceDateRangeCriteria(invoice_start=date(2026, 4, 1), invoice_end=date(2026, 4, 30)),
        InvoicePaymentStatusCriteria(payment_status="paid"),
        InvoiceCreditorCriteria(creditor_name="Creditor X"),
        InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_x.pk)),
    ]
    results = fundingrequest_query.search(*criteria).distinct()

    assert list(results) == [fr1]


@pytest.mark.django_db
def test__distinct_prevents_duplicate_funding_requests_when_multiple_positions_match_criteria() -> (
    None
):
    fr = modelfactory.fundingrequest(title="FR with Multiple Matching Positions")
    invoice = modelfactory.invoice()
    invoice.date = date(2026, 4, 15)
    invoice.status = "paid"
    creditor = modelfactory.creditor(name="Creditor Z")
    invoice.creditor = creditor
    invoice.save()

    for i in range(3):
        position = Position.objects.create(
            invoice=invoice,
            publication=fr.publication,
            description=f"Position {i+1}",
            cost_amount=Decimal("1000.00"),
            cost_currency="EUR",
            cost_type="gold-oa",
            tax_rate=Decimal("0.19"),
            external_position_id=f"POS-{i+1}",
        )
        budget = modelfactory.budget(name=f"Budget {i+1}")
        FundingAssignment.objects.create(
            position=position,
            funding_source=budget,
            amount=Decimal("1000.00"),
        )

    criteria = InvoicePaymentStatusCriteria(payment_status="paid")
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr]
