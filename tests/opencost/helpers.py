from datetime import date
from decimal import Decimal

from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract, ContractLink, ContractLinkType
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
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
    publication: Publication | None = None,
    contract: Contract | None = None,
    description: str = "APC for test article",
    cost_amount: Decimal = Decimal("1500.00"),
    cost_currency: str = "EUR",
    cost_type: str = "gold-oa",
    tax_rate: Decimal = Decimal("0.19"),
    contract_year: int | None = None,
) -> Position:
    return Position.objects.create(
        invoice=invoice,
        publication=publication,
        contract=contract,
        contract_year=contract_year,
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


def create_institution_with_identifiers(
    name: str = "Test Institution",
    ror: str | None = None,
    isni: str | None = None,
    ringold: str | None = None,
    parent: Institution | None = None,
) -> Institution:
    """Create an institution with optional ROR, ISNI, and Ringold identifiers."""
    institution = Institution.objects.create(name=name, parent=parent)

    if ror:
        ror_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
        InstitutionLink.objects.create(institution=institution, type=ror_type, value=ror)

    if isni:
        isni_type, _ = InstitutionLinkType.objects.get_or_create(name="ISNI")
        InstitutionLink.objects.create(institution=institution, type=isni_type, value=isni)

    if ringold:
        ringold_type, _ = InstitutionLinkType.objects.get_or_create(name="Ringold")
        InstitutionLink.objects.create(institution=institution, type=ringold_type, value=ringold)

    return institution


def create_corresponding_author(
    publication: Publication,
    name: str = "Test Author",
    email: str = "test@example.com",
    affiliation: Institution | None = None,
) -> Author:
    """Create a corresponding author for a publication."""
    return Author.objects.create(
        name=name,
        email=email,
        publication=publication,
        affiliation=affiliation,
        roles="CORRESPONDING_AUTHOR",
    )


def create_contract_with_identifiers(
    name: str = "Test Contract",
    start_date: date = date(2024, 1, 1),
    end_date: date = date(2024, 12, 31),
    esac: str | None = None,
    oai: str | None = None,
    ezb: str | None = None,
    local: str | None = None,
) -> Contract:
    """Create a contract with optional ESAC, OAI, EZB, and Local identifiers."""
    from coda.domain.contract import PublicationBilling

    contract = Contract.objects.create(
        name=name,
        start_date=start_date,
        end_date=end_date,
        publication_billing=PublicationBilling.Individually.value,
    )

    if esac:
        esac_type, _ = ContractLinkType.objects.get_or_create(name="ESAC")
        ContractLink.objects.create(contract=contract, type=esac_type, value=esac)

    if oai:
        oai_type, _ = ContractLinkType.objects.get_or_create(name="OAI")
        ContractLink.objects.create(contract=contract, type=oai_type, value=oai)

    if ezb:
        ezb_type, _ = ContractLinkType.objects.get_or_create(name="EZB")
        ContractLink.objects.create(contract=contract, type=ezb_type, value=ezb)

    if local:
        local_type, _ = ContractLinkType.objects.get_or_create(name="Local")
        ContractLink.objects.create(contract=contract, type=local_type, value=local)

    return contract
