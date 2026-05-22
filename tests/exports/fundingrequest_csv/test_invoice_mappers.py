"""Tests for invoice mapper layer (Models → Import DTOs)."""

import pytest
from decimal import Decimal
from datetime import date

from coda.contexts.finance.dto.import_dtos import (
    PublicationPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
)
from coda.domain.finance.costtypes import PublicationCostType, ContractCostType
from coda.domain.finance.invoice import PaymentStatus
from coda.apps.exports.services.fundingrequest_csv.mappers import (
    map_invoice_to_dto,
    _map_position_to_dto,
)
from coda.apps.invoices.models import Position, FundingAssignment, FundingSource, CurrencyConversion

from tests import modelfactory


@pytest.mark.django_db
def test__invoice__maps_to_dto__all_required_fields_are_mapped_correctly() -> None:
    creditor = modelfactory.creditor(name="Test Publisher")
    invoice = modelfactory.invoice()
    invoice.creditor = creditor
    invoice.number = "INV-2026-001"
    invoice.date = date(2026, 5, 20)
    invoice.status = "paid"
    invoice.comment = "Test invoice comment"
    invoice.external_invoice_id = "EXT-123"
    invoice.save()

    dto = map_invoice_to_dto(invoice)

    assert dto.number == "INV-2026-001"
    assert dto.date == date(2026, 5, 20)
    assert dto.creditor == "Test Publisher"
    assert dto.status == PaymentStatus.Paid
    assert dto.comment == "Test invoice comment"
    assert dto.external_id == "EXT-123"
    assert dto.conversion is None
    assert dto.positions == []


@pytest.mark.django_db
def test__invoice_with_currency_conversion__maps_to_dto__conversion_is_mapped_correctly() -> None:
    invoice = modelfactory.invoice()

    CurrencyConversion.objects.create(
        invoice=invoice, target_currency="USD", exchange_rate=Decimal("1.2500")
    )

    dto = map_invoice_to_dto(invoice)

    assert dto.conversion is not None
    assert dto.conversion.target_currency == "USD"
    assert dto.conversion.exchange_rate == Decimal("1.2500")


@pytest.mark.django_db
def test__publication_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    funding_request = modelfactory.fundingrequest(title="Test Publication")
    invoice = modelfactory.invoice()

    position = Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-001",
    )

    dto = _map_position_to_dto(position)

    assert isinstance(dto, PublicationPositionImportDto)
    assert dto.type == "publication"
    assert dto.amount == Decimal("1500.00")
    assert dto.tax_rate == Decimal("19.00")  # Converted to percentage
    assert dto.cost_type == PublicationCostType.Gold_OA
    assert dto.external_id == "POS-001"
    assert dto.request_id == str(funding_request.request_id)


@pytest.mark.django_db
def test__contract_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    contract = modelfactory.contract()
    invoice = modelfactory.invoice()

    position = Position.objects.create(
        invoice=invoice,
        contract=contract,
        contract_year=2026,
        description="Contract read fee",
        cost_amount=Decimal("2000.00"),
        cost_currency="EUR",
        cost_type="read",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-002",
    )

    dto = _map_position_to_dto(position)

    assert isinstance(dto, ContractPositionImportDto)
    assert dto.type == "contract"
    assert dto.amount == Decimal("2000.00")
    assert dto.tax_rate == Decimal("19.00")
    assert dto.cost_type == ContractCostType.Read
    assert dto.external_id == "POS-002"
    assert dto.contract_name == contract.name
    assert dto.contract_year == 2026


@pytest.mark.django_db
def test__free_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    invoice = modelfactory.invoice()

    position = Position.objects.create(
        invoice=invoice,
        publication=None,
        contract=None,
        description="Miscellaneous charges",
        cost_amount=Decimal("500.00"),
        cost_currency="EUR",
        cost_type="other",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-003",
    )

    dto = _map_position_to_dto(position)

    assert isinstance(dto, FreePositionImportDto)
    assert dto.type == "free"
    assert dto.amount == Decimal("500.00")
    assert dto.tax_rate == Decimal("19.00")
    assert dto.cost_type == PublicationCostType.Other
    assert dto.external_id == "POS-003"
    assert dto.description == "Miscellaneous charges"


@pytest.mark.django_db
def test__invoice_with_position_and_funding_assignments__maps_to_dto__maps_assignments_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest()
    invoice = modelfactory.invoice()
    institution = modelfactory.institution()

    position = Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Split publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )

    fs_budget = FundingSource.objects.create(type="budget", name="Budget 2026")
    fs_institution = FundingSource.objects.create(
        type="institution", name=institution.name, institution=institution
    )

    FundingAssignment.objects.create(
        position=position, funding_source=fs_budget, amount=Decimal("1000.00")
    )
    FundingAssignment.objects.create(
        position=position, funding_source=fs_institution, amount=Decimal("500.00")
    )

    dto = _map_position_to_dto(position)

    assert len(dto.funding_assignments) == 2
    assert dto.funding_assignments[0].name == "Budget 2026"
    assert dto.funding_assignments[0].type == "budget"
    assert dto.funding_assignments[0].amount == Decimal("1000.00")
    assert dto.funding_assignments[1].name == institution.name
    assert dto.funding_assignments[1].type == "institution"
    assert dto.funding_assignments[1].amount == Decimal("500.00")


@pytest.mark.django_db
def test__invoice_with_multiple_positions__maps_to_dto__maps_all_positions_correctly() -> None:
    funding_request = modelfactory.fundingrequest()
    contract = modelfactory.contract()
    invoice = modelfactory.invoice()

    # Create different position types
    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Pub charge",
        cost_amount=Decimal("1000.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )
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

    dto = map_invoice_to_dto(invoice)

    assert len(dto.positions) == 3
    assert isinstance(dto.positions[0], PublicationPositionImportDto)
    assert isinstance(dto.positions[1], ContractPositionImportDto)
    assert isinstance(dto.positions[2], FreePositionImportDto)
    assert dto.positions[0].amount == Decimal("1000.00")
    assert dto.positions[1].amount == Decimal("2000.00")
    assert dto.positions[2].amount == Decimal("300.00")
