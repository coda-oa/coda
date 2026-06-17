import pytest
from datetime import date
from decimal import Decimal

from tests import modelfactory
from coda.apps.invoices.models import FundingAssignment, Position

from coda.apps.exports.services.fundingrequest_csv.criteria import (
    InvoiceFundingSourceCriteria,
)
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchCriteria
from coda.domain.finance.invoice import FundingSourceId


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
        InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_x.pk)),
    ]
    results = fundingrequest_query.search(*criteria).distinct()

    assert list(results) == [fr1]
