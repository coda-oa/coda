from decimal import Decimal
from datetime import date

import pytest

from coda.apps.invoices.models import Position
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.contexts.finance.dto.import_dtos import PublicationPositionImportDto
from coda.domain.finance.costtypes import PublicationCostType
from tests import modelfactory


@pytest.mark.django_db
def test__funding_request_with_invoice__mapping_to_export_dto__data_is_mapped_correctly() -> None:
    funding_request = modelfactory.fundingrequest(title="Test Publication for Export")

    invoice = modelfactory.invoice()
    invoice.number = "INV-001"
    invoice.date = date(2026, 5, 1)
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=funding_request.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-001",
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
    funding_request = modelfactory.fundingrequest(title="Test Publication for Export")

    invoice1 = modelfactory.invoice()
    invoice1.number = "INV-001"
    invoice1.date = date(2026, 5, 1)
    invoice1.save()

    invoice2 = modelfactory.invoice()
    invoice2.number = "INV-002"
    invoice2.date = date(2026, 5, 15)
    invoice2.save()

    Position.objects.create(
        invoice=invoice1,
        publication=funding_request.publication,
        description="Publication charge - Invoice 1",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),  # 19% as fraction
        external_position_id="POS-001",
    )
    Position.objects.create(
        invoice=invoice2,
        publication=funding_request.publication,
        description="Color charge - Invoice 2",
        cost_amount=Decimal("300.00"),
        cost_currency="EUR",
        cost_type="colour charge",
        tax_rate=Decimal("0.07"),  # 7% as fraction
        external_position_id="POS-002",
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
    assert position1_dto.tax_rate == Decimal("19.00")  # Converted to percentage!
    assert position1_dto.cost_type == PublicationCostType.Gold_OA
    assert position1_dto.external_id == "POS-001"

    assert composite_dto.invoices[1].number == "INV-002"
    assert composite_dto.invoices[1].date == date(2026, 5, 15)
    assert len(composite_dto.invoices[1].positions) == 1

    position2_dto = composite_dto.invoices[1].positions[0]
    assert position2_dto.amount == Decimal("300.00")
    assert position2_dto.tax_rate == Decimal("7.00")  # Converted to percentage!
    assert position2_dto.cost_type == PublicationCostType.Colour_Charge


@pytest.mark.django_db
def test__funding_request_without_invoices__mapping_to_export_dto__maps_to_dto_with_empty_invoice_list() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Unpaid Publication")

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == "Unpaid Publication"

    assert composite_dto.invoices == []
    assert len(composite_dto.invoices) == 0
