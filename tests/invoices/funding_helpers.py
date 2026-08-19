from decimal import Decimal

from coda.apps.invoices.models import FundingAssignment, FundingSource, Invoice, Position
from tests import modelfactory


def create_assignment(
    funding_source: FundingSource,
    amount: str | Decimal,
    currency: str = "EUR",
    invoice: Invoice | None = None,
    status: str | None = None,
) -> Invoice:
    """Creates a position + funding assignment on a (new or given) invoice.

    If ``status`` is given, the invoice's payment status is set before the
    assignment is created.
    """
    if invoice is None:
        invoice = modelfactory.invoice()

    if status is not None:
        invoice.status = status
        invoice.save()

    position = Position.objects.create(
        description="Test position",
        cost_amount=amount,
        cost_currency=currency,
        invoice=invoice,
    )
    FundingAssignment.objects.create(
        position=position, funding_source=funding_source, amount=amount
    )
    return invoice
