from decimal import Decimal
from datetime import date

import pytest

from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.contexts.finance.dto.import_dtos import PublicationPositionImportDto
from coda.domain.finance.costtypes import PublicationCostType
from tests.exports.fundingrequest_csv.helpers import (
    create_funding_request_with_invoice_and_publication_position,
    create_funding_request_with_invoices,
    create_funding_request_without_invoices,
)


@pytest.mark.django_db
def test__funding_request_with_invoice__mapping_to_export_dto__data_is_mapped_correctly() -> None:
    funding_request = create_funding_request_with_invoice_and_publication_position(
        title="Test Publication for Export",
        invoice_number="INV-001",
        invoice_date=date(2026, 5, 1),
        cost_amount=Decimal("1500.00"),
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == "Test Publication for Export"
    assert composite_dto.funding_request.legacy_request_id == str(funding_request.legacy_request_id)

    assert composite_dto.invoices[0].number == "INV-001"
    assert composite_dto.invoices[0].date == date(2026, 5, 1)

    position_dto = composite_dto.invoices[0].positions[0]
    assert position_dto.amount == Decimal("1500.00")
    assert position_dto.tax_rate == Decimal("19.00")  # Converted to percentage!
    assert position_dto.cost_type == PublicationCostType.Gold_OA


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__mapping_to_export_dto__invoices__maps_to_composite_export_dto() -> (
    None
):
    funding_request = create_funding_request_with_invoices(
        title="Test Publication for Export",
        num_invoices=2,
        base_invoice_number="INV-",
        base_invoice_date=date(2026, 5, 1),
        cost_amounts=[Decimal("1500.00"), Decimal("300.00")],
        cost_types=["gold-oa", "colour charge"],
        tax_rates=[Decimal("0.19"), Decimal("0.07")],
    )

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == "Test Publication for Export"
    assert composite_dto.funding_request.legacy_request_id == str(funding_request.legacy_request_id)

    assert composite_dto.invoices[0].number == "INV-001"
    assert composite_dto.invoices[0].date == date(2026, 5, 1)
    assert len(composite_dto.invoices[0].positions) == 1

    position1_dto = composite_dto.invoices[0].positions[0]
    assert isinstance(position1_dto, PublicationPositionImportDto)
    assert position1_dto.amount == Decimal("1500.00")
    assert position1_dto.tax_rate == Decimal("19.00")
    assert position1_dto.cost_type == PublicationCostType.Gold_OA
    assert position1_dto.external_id == "POS-001"

    assert composite_dto.invoices[1].number == "INV-002"
    assert composite_dto.invoices[1].date == date(2026, 5, 15)
    assert len(composite_dto.invoices[1].positions) == 1

    position2_dto = composite_dto.invoices[1].positions[0]
    assert position2_dto.amount == Decimal("300.00")
    assert position2_dto.tax_rate == Decimal("7.00")
    assert position2_dto.cost_type == PublicationCostType.Colour_Charge


@pytest.mark.django_db
def test__funding_request_without_invoices__mapping_to_export_dto__maps_to_dto_with_empty_invoice_list() -> (
    None
):
    funding_request = create_funding_request_without_invoices(title="Unpaid Publication")

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == "Unpaid Publication"
    assert composite_dto.invoices == []
    assert len(composite_dto.invoices) == 0
