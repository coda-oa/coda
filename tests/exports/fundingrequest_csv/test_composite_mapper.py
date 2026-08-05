from datetime import date

import pytest

from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from tests.exports.helpers import (
    create_funding_request,
    create_invoice_with_publication_position,
)


@pytest.mark.django_db
def test__funding_request_with_invoice__mapping_to_export_dto__data_is_mapped_correctly() -> None:
    funding_request = create_funding_request(
        title="Test Publication for Export",
        request_date=date(2026, 5, 1),
    )
    invoice = create_invoice_with_publication_position(funding_request=funding_request)

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == funding_request.publication.title
    assert composite_dto.funding_request.legacy_request_id == str(funding_request.legacy_request_id)

    assert composite_dto.invoices[0].number == invoice.number
    assert composite_dto.invoices[0].date == invoice.date

    position_dto = composite_dto.invoices[0].positions[0]
    actual_position = next(iter(invoice.positions))
    assert actual_position is not None, "Invoice should have at least one position"
    assert position_dto.amount == actual_position.cost.amount
    assert position_dto.tax_rate == actual_position.tax_rate * 100  # Converted to percentage!
    assert position_dto.cost_type.value == actual_position.item.cost_type.value


@pytest.mark.django_db
def test__funding_request_with_multiple_invoices__mapping_to_export_dto__invoices__maps_to_composite_export_dto() -> (
    None
):
    funding_request = create_funding_request(
        title="Test Publication for Export",
        request_date=date(2026, 5, 1),
    )
    invoice_1 = create_invoice_with_publication_position(funding_request=funding_request)
    invoice_2 = create_invoice_with_publication_position(funding_request=funding_request)

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == funding_request.publication.title
    assert composite_dto.funding_request.legacy_request_id == str(funding_request.legacy_request_id)

    invoice_numbers = {inv.number for inv in composite_dto.invoices}
    assert invoice_1.number in invoice_numbers
    assert invoice_2.number in invoice_numbers

    invoice_dto_by_number = {inv.number: inv for inv in composite_dto.invoices}

    invoice_1_dto = invoice_dto_by_number[invoice_1.number]
    assert invoice_1_dto.date == invoice_1.date

    position1_dto = invoice_1_dto.positions[0]
    domain_position_1 = next(iter(invoice_1.positions))

    assert position1_dto.amount == domain_position_1.cost.amount
    assert position1_dto.tax_rate == domain_position_1.tax_rate.percentage()
    assert position1_dto.cost_type.value == domain_position_1.item.cost_type.value
    assert position1_dto.external_id == domain_position_1.external_position_id

    invoice_2_dto = invoice_dto_by_number[invoice_2.number]
    assert invoice_2_dto.date == invoice_2.date

    position2_dto = invoice_2_dto.positions[0]
    domain_position_2 = next(iter(invoice_2.positions))

    assert position2_dto.amount == domain_position_2.cost.amount
    assert position2_dto.tax_rate == domain_position_2.tax_rate.percentage()
    assert position2_dto.cost_type.value == domain_position_2.item.cost_type.value
    assert position2_dto.external_id == domain_position_2.external_position_id


@pytest.mark.django_db
def test__funding_request_without_invoices__mapping_to_export_dto__maps_to_dto_with_empty_invoice_list() -> (
    None
):
    funding_request = create_funding_request(
        title="Unpaid Publication",
        request_date=date(2026, 5, 1),
    )

    composite_dto = map_funding_request_to_export_dto(funding_request)

    assert composite_dto.funding_request.publication.title == funding_request.publication.title
    assert composite_dto.invoices == []
    assert len(composite_dto.invoices) == 0
