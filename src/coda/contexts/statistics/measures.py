"""Gross money rules for the statistics page (plan §6, ADR-0001).

Positions and assignments are stored *net of tax*, so raw sums are not spend. The
arithmetic itself lives in the domain's cost calculation classes; this module only
selects the right one and never restates the calculation.
"""

from decimal import Decimal

from coda.domain.finance.invoice_positions import RegularCostCalculation, VatCalculation
from coda.domain.finance.taxable_money import CostBasis, NetMoney
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money

VAT_COST_TYPE = "vat"


def is_vat_cost_type(cost_type: str) -> bool:
    """The same string test the openCost invoice line uses for unmapped cost types."""
    return cost_type == VAT_COST_TYPE


def gross_of(cost: Money, tax_rate: TaxRate, *, is_vat: bool) -> Money:
    """Gross of one invoice position's stored cost.

    A regular position's cost is net, so its gross is cost plus the position's tax
    rate. A ``vat``-type position's amount *is* the tax, so it is already the gross
    amount and its tax rate plays no role (ADR-0001).
    """
    calculation = (
        VatCalculation(cost)
        if is_vat
        else RegularCostCalculation(NetMoney.from_money(cost, tax_rate))
    )
    return calculation.total()


def gross_assignment(
    amount: Decimal, tax_rate: TaxRate, currency: Currency, *, is_vat: bool
) -> Money:
    """Gross of one funding assignment's stored net amount.

    Gross of a regular assignment is net plus the position's tax rate; an assignment
    on a ``vat`` position is unchanged, mirroring :func:`gross_of`.
    """
    if is_vat:
        return Money(amount, currency)

    return NetMoney(amount, currency, tax_rate).amount_in(CostBasis.gross)
