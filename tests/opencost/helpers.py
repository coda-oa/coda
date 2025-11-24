from datetime import date
from decimal import Decimal

from coda.apps.invoices.models import Creditor, Invoice, Position
from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.report_service import generate_report
from coda.apps.publications.models import Publication


def create_creditor(name: str = "Test Creditor") -> Creditor:
    return Creditor.objects.create(name=name)


def create_invoice(
    creditor: Creditor | None = None,
    invoice_date: date = date(2024, 6, 1),
    number: str = "INV-2024-001",
    status: str = "paid",
) -> Invoice:
    if creditor is None:
        creditor = create_creditor()

    return Invoice.objects.create(
        creditor=creditor,
        date=invoice_date,
        number=number,
        status=status,
    )


def create_position(
    invoice: Invoice,
    publication: Publication,
    description: str = "APC for test article",
    cost_amount: Decimal = Decimal("1500.00"),
    cost_currency: str = "EUR",
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
) -> Position:
    return Position.objects.create(
        invoice=invoice,
        publication=publication,
        description=description,
        cost_amount=cost_amount,
        cost_currency=cost_currency,
        cost_type=cost_type,
        tax_rate=tax_rate,
    )


def create_publication_with_invoice(
    publication: Publication,
    invoice_date: date = date(2024, 6, 1),
    invoice_number: str = "INV-2024-001",
    creditor_name: str = "Test Creditor",
    cost_amount: Decimal = Decimal("1500.00"),
    cost_currency: str = "EUR",
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
) -> tuple[Invoice, Position]:
    creditor = create_creditor(name=creditor_name)
    invoice = create_invoice(
        creditor=creditor,
        invoice_date=invoice_date,
        number=invoice_number,
    )
    position = create_position(
        invoice=invoice,
        publication=publication,
        cost_amount=cost_amount,
        cost_currency=cost_currency,
        cost_type=cost_type,
        tax_rate=tax_rate,
    )
    return invoice, position


def create_opencost_report(
    title: str = "Test OpenCost Report 2024",
    period_start: date = date(2024, 1, 1),
    period_end: date = date(2024, 12, 31),
) -> OpenCostReport:
    return generate_report(
        title=title,
        period_start=period_start,
        period_end=period_end,
    )
