import pytest
from datetime import date
from decimal import Decimal

from tests import modelfactory
from coda.contexts.finance.services import invoice_service
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice
from coda.domain.finance.invoice_positions import PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.fundingrequest_query import (
    InvoiceFundingSourceCriteria,
)
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchCriteria
from coda.apps.invoices.models import Creditor as CreditorModel
from coda.domain.finance.invoice_positions import Position


def _create_invoice_with_position(
    funding_request: FundingRequest,
    *,
    number: str,
    date_value: date,
    cost_amount: Decimal,
    external_position_id: str,
    creditor_name: str = "Creditor",
) -> tuple[CreditorModel, Position]:
    creditor = modelfactory.creditor(name=creditor_name)
    position = invoice_positions.create(
        item=PublicationItem(
            item=PublicationId(funding_request.publication.id),
            cost_type=PublicationCostType("gold-oa"),
        ),
        cost=Money(cost_amount, Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id=external_position_id,
    )
    return creditor, position


def _save_invoice(
    creditor: CreditorModel, position: Position, *, number: str, date_value: date
) -> Invoice:
    invoice = Invoice.new(
        number=number,
        date=date_value,
        creditor=CreditorId(creditor.pk),
        positions=[position],
    )
    invoice.id = invoice_service.save(invoice)
    return invoice


@pytest.mark.django_db
def test__funding_request_with_invoice__filtered_by_funding_source__returns_only_funding_requests_with_invoices_matching_funding_source() -> (
    None
):
    fr_funding_source_a = modelfactory.fundingrequest(title="Funding Source A Invoice")
    budget_model_a = modelfactory.budget(name="Funding Source A")
    budget_a = Budget(FundingSourceId(budget_model_a.pk), budget_model_a.name)

    creditor_a, position_a = _create_invoice_with_position(
        fr_funding_source_a,
        number="INV-A",
        date_value=date(2024, 1, 1),
        cost_amount=Decimal("1500.00"),
        external_position_id="POS-FUNDING-SOURCE-A",
        creditor_name="Creditor A",
    )
    position_a.assign_funding(budget_a, Decimal("1500.00"))
    _save_invoice(creditor_a, position_a, number="INV-A", date_value=date(2024, 1, 1))

    fr_funding_source_b = modelfactory.fundingrequest(title="Funding Source B Invoice")
    budget_model_b = modelfactory.budget(name="Funding Source B")
    budget_b = Budget(FundingSourceId(budget_model_b.pk), budget_model_b.name)

    creditor_b, position_b = _create_invoice_with_position(
        fr_funding_source_b,
        number="INV-B",
        date_value=date(2024, 1, 1),
        cost_amount=Decimal("2000.00"),
        external_position_id="POS-FUNDING-SOURCE-B",
        creditor_name="Creditor B",
    )
    position_b.assign_funding(budget_b, Decimal("2000.00"))
    _save_invoice(creditor_b, position_b, number="INV-B", date_value=date(2024, 1, 1))

    criteria = InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_model_a.pk))
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_funding_source_a]


@pytest.mark.django_db
def test__combining_multiple_criteria__filters_funding_requests_correctly() -> None:
    fr1 = modelfactory.fundingrequest(title="FR 1")
    budget_model_x = modelfactory.budget(name="Budget X")
    budget_x = Budget(FundingSourceId(budget_model_x.pk), budget_model_x.name)
    creditor_1, position_1 = _create_invoice_with_position(
        fr1,
        number="INV-1",
        date_value=date(2026, 4, 10),
        cost_amount=Decimal("1000.00"),
        external_position_id="POS-1",
        creditor_name="Creditor X",
    )
    position_1.assign_funding(budget_x, Decimal("1000.00"))
    _save_invoice(creditor_1, position_1, number="INV-1", date_value=date(2026, 4, 10))

    fr2 = modelfactory.fundingrequest(title="FR 2")
    budget_model_y = modelfactory.budget(name="Budget Y")
    budget_y = Budget(FundingSourceId(budget_model_y.pk), budget_model_y.name)
    creditor_2, position_2 = _create_invoice_with_position(
        fr2,
        number="INV-2",
        date_value=date(2026, 5, 20),
        cost_amount=Decimal("2000.00"),
        external_position_id="POS-2",
        creditor_name="Creditor Y",
    )
    position_2.assign_funding(budget_y, Decimal("2000.00"))
    _save_invoice(creditor_2, position_2, number="INV-2", date_value=date(2026, 5, 20))

    criteria: list[FundingRequestSearchCriteria] = [
        InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_model_x.pk)),
    ]
    results = fundingrequest_query.search(*criteria).distinct()

    assert list(results) == [fr1]
