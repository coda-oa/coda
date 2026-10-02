from decimal import Decimal

import pytest

from coda.apps.opencost.transformers.invoices import OpenCostInvoiceLine
from coda.domain.finance.costtypes import PublicationCostType as DomainPublicationCostType
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money


def test_regular_position_uses_regular_cost_and_tax_calculations() -> None:
    line = OpenCostInvoiceLine.from_position(
        cost=Money(Decimal("1000.01"), Currency.EUR),
        cost_type=DomainPublicationCostType.Gold_OA,
        tax_rate=TaxRate("0.19"),
    )

    assert line.amount_paid.amount == Decimal("1000.01")
    assert line.amount_paid.currency is Currency.EUR
    assert line.cost_type is DomainPublicationCostType.Gold_OA
    assert line.vat is not None
    assert line.vat.amount == Decimal("190.00")
    assert line.vat.currency is Currency.EUR
    assert line.invoice_net_contribution.amount == Decimal("1000.01")
    assert line.invoice_net_contribution.currency is Currency.EUR


def test_separate_vat_position_is_an_amount_not_a_tax_field() -> None:
    line = OpenCostInvoiceLine.from_position(
        cost=Money(Decimal("285.00"), Currency.EUR),
        cost_type=DomainPublicationCostType.Vat,
        tax_rate=TaxRate("0.19"),
    )

    assert line.amount_paid.amount == Decimal("285.00")
    assert line.amount_paid.currency is Currency.EUR
    assert line.cost_type is DomainPublicationCostType.Vat
    assert line.vat is None
    assert line.invoice_net_contribution.amount == Decimal("0.00")
    assert line.invoice_net_contribution.currency is Currency.EUR


def test_invoice_line_rejects_monetary_fields_with_different_currencies() -> None:
    with pytest.raises(ValueError, match="same currency"):
        OpenCostInvoiceLine(
            amount_paid=Money(Decimal("100.00"), Currency.EUR),
            cost_type=DomainPublicationCostType.Gold_OA,
            vat=Money(Decimal("19.00"), Currency.USD),
        )
