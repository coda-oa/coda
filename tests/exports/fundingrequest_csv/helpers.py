from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams
from coda.apps.invoices.models import (
    Invoice,
    Position,
    FundingAssignment,
    FundingSource,
    CurrencyConversion,
)
from coda.domain.date import DateRange
from tests import modelfactory


def _make_params(
    period_start: date,
    period_end: date,
    **kwargs: Any,
) -> FundingRequestSearchParams:
    return FundingRequestSearchParams(
        date_range=DateRange(period_start, period_end),
        **kwargs,
    )


def create_funding_request_with_invoice_and_publication_position(
    title: str = "Test Publication",
    invoice_number: str = "INV-001",
    invoice_date: date = date(2026, 5, 1),
    cost_amount: Decimal = Decimal("1500.00"),
    cost_currency: str = "EUR",
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
    external_position_id: str = "POS-001",
) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.request_date = invoice_date
    funding_request.save()

    invoice = modelfactory.invoice()
    invoice.number = invoice_number
    invoice.date = invoice_date
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=cost_amount,
        cost_currency=cost_currency,
        cost_type=cost_type,
        tax_rate=tax_rate,
        external_position_id=external_position_id,
    )

    return funding_request


def create_funding_request_with_invoices(
    title: str = "Test Publication",
    num_invoices: int = 2,
    base_invoice_number: str = "INV-",
    base_invoice_date: date = date(2026, 5, 1),
    cost_amounts: list[Decimal] | None = None,
    cost_types: list[str] | None = None,
    tax_rates: list[Decimal] | None = None,
) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.request_date = base_invoice_date
    funding_request.save()

    if cost_amounts is None:
        cost_amounts = [Decimal("1500.00")] * num_invoices
    if cost_types is None:
        cost_types = ["gold-oa"] * num_invoices
    if tax_rates is None:
        tax_rates = [Decimal("0.19")] * num_invoices

    for i in range(num_invoices):
        invoice = modelfactory.invoice()
        invoice.number = f"{base_invoice_number}{i+1:03d}"
        invoice.date = base_invoice_date + timedelta(days=i * 14)
        invoice.save()

        Position.objects.create(
            invoice=invoice,
            publication=funding_request.publication,
            description=f"Publication charge - Invoice {i+1}",
            cost_amount=cost_amounts[i],
            cost_currency="EUR",
            cost_type=cost_types[i],
            tax_rate=tax_rates[i],
            external_position_id=f"POS-{i+1:03d}",
        )

    return funding_request


def create_funding_request_without_invoices(
    title: str = "Unpaid Publication",
) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.request_date = date(2026, 5, 1)
    funding_request.save()
    return funding_request


def create_invoice_with_funding_assignments(
    funding_request: FundingRequest,
    invoice_number: str = "INV-001",
    invoice_date: date = date(2026, 5, 1),
    cost_amount: Decimal = Decimal("1500.00"),
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
    budget_name: str = "Budget 2026",
    budget_amount: Decimal = Decimal("1000.00"),
    institution_name: str = "Test Institution",
    institution_amount: Decimal = Decimal("500.00"),
) -> "Invoice":
    """Create an invoice with two funding assignments (budget + institution)."""
    invoice = modelfactory.invoice()
    invoice.number = invoice_number
    invoice.date = invoice_date
    invoice.save()

    position = Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Split publication charge",
        cost_amount=cost_amount,
        cost_currency="EUR",
        cost_type=cost_type,
        tax_rate=tax_rate,
    )

    institution = modelfactory.institution()
    institution.name = institution_name
    institution.save()
    fs_budget = FundingSource.objects.create(type="budget", name=budget_name)
    fs_institution = FundingSource.objects.create(
        type="institution", name=institution_name, institution=institution
    )

    FundingAssignment.objects.create(
        position=position, funding_source=fs_budget, amount=budget_amount
    )
    FundingAssignment.objects.create(
        position=position, funding_source=fs_institution, amount=institution_amount
    )

    return invoice


def create_invoice_with_currency_conversion(
    funding_request: FundingRequest,
    invoice_number: str = "INV-001",
    invoice_date: date = date(2026, 5, 1),
    target_currency: str = "USD",
    exchange_rate: Decimal = Decimal("1.2500"),
) -> "Invoice":
    """Create an invoice with a currency conversion."""
    invoice = modelfactory.invoice()
    invoice.number = invoice_number
    invoice.date = invoice_date
    invoice.save()

    CurrencyConversion.objects.create(
        invoice=invoice, target_currency=target_currency, exchange_rate=exchange_rate
    )

    return invoice


def create_invoice_with_mixed_positions(
    funding_request: FundingRequest,
    contract: "Contract",
    invoice_number: str = "INV-001",
    invoice_date: date = date(2026, 5, 1),
) -> "Invoice":
    invoice = modelfactory.invoice()
    invoice.number = invoice_number
    invoice.date = invoice_date
    invoice.save()

    # Publication position
    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Pub charge",
        cost_amount=Decimal("1000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )
    # Contract position
    Position.objects.create(
        invoice=invoice,
        contract=contract,
        contract_year=2026,
        description="Contract fee",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="read",
        tax_rate=Decimal("0.19"),
    )
    # Free position
    Position.objects.create(
        invoice=invoice,
        publication=None,
        contract=None,
        description="Misc",
        cost_amount=Decimal("300.00"),
        cost_currency="EUR",
        cost_type="other",
        tax_rate=Decimal("0.19"),
    )
    return invoice
