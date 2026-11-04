"""Dedicated setup helpers for the budget test suites.

Complex setups live here, not in ``modelfactory`` (which stays a home for
simple row factories). Where sensible the helpers speak the domain language —
``Budget``, ``Money`` — and only drop down to Django models where the ORM or
a not-yet-built write path requires it."""

from decimal import Decimal

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.invoices import repository as invoice_repository
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.domain.finance.invoice_positions import FreeItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId
from tests import domainfactory, modelfactory


def a_budget(
    *, name: str = "DARK 2026", amount: Money | None = None
) -> tuple[Budget, FundingSourceId]:
    """A persisted budget, returned as a domain object alongside its id."""
    amount = amount or Money("10000", Currency.EUR)
    row = modelfactory.budget(name=name, amount=amount)
    budget = Budget.new(row.name, amount=amount, period=DateRange.year(2026))
    budget.id = FundingSourceId(row.pk)
    return budget, budget.id


def an_unsaved_invoice_with_assignment(
    cost: Money,
    budget: Budget,
    *,
    conversion_rate: Decimal | None = None,
    publication: PublicationId | None = None,
) -> Invoice:
    """A domain invoice with one position whose full cost is assigned to the
    given budget — not persisted; callers decide how to save it."""
    assert budget.id is not None
    if publication is not None:
        item: invoice_positions.PositionItemType = invoice_positions.PublicationItem(
            publication, cost_type=PublicationCostType.Gold_OA
        )
    else:
        item = FreeItem("APC", cost_type=PublicationCostType.Gold_OA)
    position = invoice_positions.create(
        item=item,
        cost=cost,
        tax_rate=TaxRate.from_percentage(0),
        external_position_id="POS-1",
    )
    position.assign_funding(budget, cost.amount)

    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position]
    )
    invoice.status = PaymentStatus.Unpaid
    if conversion_rate is not None:
        invoice.add_conversion(conversion_rate, Currency.EUR)
    return invoice


def an_invoice_with_assignment(
    cost: Money,
    budget: Budget,
    *,
    paid: bool = False,
    conversion_rate: Decimal | None = None,
    publication: PublicationId | None = None,
) -> None:
    """Seed a persisted invoice with one position whose full cost is assigned
    to the given budget, through the domain layer. Pass a publication id to
    link the position (and thus the assignment) to a funding request."""
    invoice = an_unsaved_invoice_with_assignment(
        cost, budget, conversion_rate=conversion_rate, publication=publication
    )
    if paid:
        invoice.pay()
    invoice_repository.create(invoice)


def an_approved_funding_request(*, decided_funding: Money) -> FundingRequestModel:
    """A funding request whose review is approved with the decided amount."""
    funding_request = modelfactory.fundingrequest()
    review = funding_request.review
    review.review_result = "approved"
    review.decided_funding_amount = decided_funding.amount
    review.decided_funding_currency = decided_funding.currency.code
    review.save()
    return funding_request


def a_review_split(funding_request: FundingRequestModel, budget: Budget, amount: Money) -> None:
    """Attribute part of a decided funding request to a budget."""
    assert budget.id is not None
    funding_request.review.funding_splits.create(funding_source_id=budget.id, amount=amount.amount)
