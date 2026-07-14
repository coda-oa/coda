from typing import cast, Any
from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract, ContractLink, ContractLinkType
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.invoices.models import Creditor, Invoice, Position
from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.report_service import generate_report
from coda.apps.opencost.transformers import report_publication_to_pydantic, to_opencost
from coda.apps.publications.models import Publication
from coda.domain.opencost import Data
from coda.domain.opencost._publication import PublicationType
from coda.apps.publications.models._attachedentities import AttachedContract

from tests import modelfactory


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
    filters = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }
    return generate_report(
        title=title,
        filters=filters,
    )


def transform_first_publication_to_pydantic() -> PublicationType:
    """
    Helper to create an OpenCost report and transform its first publication to pydantic.

    This eliminates the repeated pattern of:
    - Creating a report
    - Getting the first publication
    - Asserting it's not None
    - Transforming it to pydantic

    Returns the transformed PublicationType for assertions.
    """
    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    return report_publication_to_pydantic(report_publication)


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

    contract = modelfactory.contract()
    contract.name = name
    contract.start_date = start_date
    contract.end_date = end_date
    contract.save()

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


def create_contract_with_invoice(
    contract: Contract,
    creditor_name: str = "Contract Creditor",
    invoice_date: date = date(2024, 7, 1),
    invoice_number: str = "INV-CONTRACT-001",
    position_descriptions: list[str] | None = None,
    position_amounts: list[Decimal] | None = None,
    cost_type: str = "publish",
) -> tuple[Invoice, list[Position]]:
    """
    Create an invoice with positions for a contract.

    If position_descriptions and position_amounts are not provided,
    creates a single position with default values.
    """
    creditor = create_creditor(name=creditor_name)
    invoice = create_invoice(
        creditor=creditor,
        invoice_date=invoice_date,
        number=invoice_number,
        status="paid",
    )

    # Default to single position if not specified
    if position_descriptions is None:
        position_descriptions = ["Service Fee Part 1"]
    if position_amounts is None:
        position_amounts = [Decimal("1200.00")]

    positions = []
    for desc, amount in zip(position_descriptions, position_amounts):
        position = create_position(
            invoice,
            contract=contract,
            description=desc,
            cost_amount=amount,
            cost_type=cost_type,
        )
        positions.append(position)

    return invoice, positions


def generate_opencost_report_from_contract() -> Data:
    """
    Helper to generate an OpenCost report and transform to OpenCostData.

    This eliminates the repeated pattern of:
    - Generating a report with standard date range
    - Transforming it to opencost format
    - Initial contract assertions

    Returns the transformed Data for assertions.
    """
    filters = {
        "period_start": date(2024, 1, 1).isoformat(),
        "period_end": date(2024, 12, 31).isoformat(),
    }
    report = generate_report(
        title="Test Report 2024",
        filters=filters,
    )
    return to_opencost(report)


def create_realistic_report_data(
    num_publications: int = 100,
    num_contracts: int = 10,
    period_start: date = date(2024, 1, 1),
    period_end: date = date(2024, 12, 31),
) -> OpenCostReport:
    """
    Create realistic test data for performance testing.

    Args:
        num_publications: Number of publications to create
        num_contracts: Number of contracts to create
        period_start: Start of reporting period
        period_end: End of reporting period

    Returns:
        OpenCostReport with realistic data volumes
    """

    # Create contracts with invoices
    contracts = []
    for i in range(num_contracts):
        contract = modelfactory.contract()
        contract.name = f"Contract {i + 1}"
        contract.save()
        create_contract_with_invoice(
            contract,
            creditor_name=f"Contract Creditor {i + 1}",
            invoice_date=date(2024, 6, (i % 28) + 1),
            invoice_number=f"INV-CONTRACT-{i + 1:04d}",
            position_amounts=[Decimal("5000.00"), Decimal("3000.00")],
        )
        contracts.append(contract)

    # Create publications with invoices
    publications = []
    for i in range(num_publications):
        publication = modelfactory.publication()
        publication.title = f"Publication {i + 1}"
        publication.save()
        create_publication_with_invoice(
            publication,
            invoice_date=date(2024, 6, ((i * 7) % 28) + 1),
            invoice_number=f"INV-PUB-{i + 1:04d}",
            creditor_name=f"Publisher {(i % 20) + 1}",
            cost_amount=Decimal("1500.00"),
        )

        # Link some publications to contracts (50% of publications)
        if i % 2 == 0:
            AttachedContract.objects.create(
                contract=contracts[i % num_contracts],
                publication=publication,
                contract_year=2024,
            )

        publications.append(publication)

    # Generate the report
    return generate_report(
        title=f"Performance Test Report ({num_publications} pubs, {num_contracts} contracts)",
        filters={
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        },
    )


def assert_current_filter(response: HttpResponse, field: str, expected: Any) -> None:
    """Assert that a filter value in the template context matches expected."""
    context = cast(Any, response).context
    current_filters = context.get("current_filters", {})
    assert field in current_filters, (
        f"Field '{field}' not found in current_filters. "
        f"Available: {list(current_filters.keys())}"
    )
    actual = current_filters[field]
    assert actual == expected, (
        f"Field '{field}' mismatch.\n" f"Expected: {expected!r}\n" f"Got: {actual!r}"
    )


def assert_current_filters(response: HttpResponse, **expected: Any) -> None:
    """Assert multiple filter values at once."""
    for field, expected_value in expected.items():
        assert_current_filter(response, field, expected_value)


def get_opencost_generate_response(client: Client, **filters: str | list[str]) -> HttpResponse:
    return cast(HttpResponse, client.get(reverse("opencost:generate"), filters))
