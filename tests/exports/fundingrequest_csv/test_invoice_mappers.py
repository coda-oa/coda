"""Tests for invoice mapper layer (Models → Import DTOs)."""

import pytest
from decimal import Decimal

from coda.contexts.finance.dto.import_dtos import (
    PublicationPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
)
from coda.apps.exports.services.fundingrequest_csv.mappers import (
    map_invoice_to_dto,
)

from coda.domain.finance.invoice_positions import ContractItem
from tests import modelfactory
from tests.exports.fundingrequest_csv.helpers import (
    create_funding_request,
    create_invoice_with_funding_assignments,
    create_invoice_with_currency_conversion,
    create_invoice_with_mixed_positions,
    create_invoice_with_free_position,
    create_invoice_with_publication_position,
    create_invoice_with_contract_position,
)
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.domain.money import Currency
from coda.apps.contracts.mappers._domain import ContractDomainMapper
from tests import domainfactory


@pytest.mark.django_db
def test__invoice__maps_to_dto__all_required_fields_are_mapped_correctly() -> None:
    fr = create_funding_request(title="Test Publication")
    invoice = create_invoice_with_publication_position(fr)
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    dto = map_invoice_to_dto(invoice_model, fr)

    assert dto.number == invoice.number
    assert dto.date == invoice.date
    assert dto.creditor == invoice_model.creditor.name
    assert dto.status == invoice.status
    assert dto.comment == invoice.comment
    assert dto.external_id == invoice.external_invoice_id
    assert dto.conversion is None


@pytest.mark.django_db
def test__invoice_with_currency_conversion__maps_to_dto__conversion_is_mapped_correctly() -> None:
    target_currency = Currency.USD
    fr = create_funding_request(title="Test")
    invoice = create_invoice_with_currency_conversion(
        target_currency=target_currency,
        exchange_rate=Decimal("2.0000"),
    )
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    dto = map_invoice_to_dto(invoice_model, fr)

    assert dto.conversion is not None
    assert dto.conversion.target_currency == str(target_currency.code)
    assert dto.conversion.exchange_rate == invoice.conversions()[target_currency]


@pytest.mark.django_db
def test__publication_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    fr = create_funding_request(title="Test Publication")
    invoice = create_invoice_with_publication_position(fr)
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    invoice_dto = map_invoice_to_dto(invoice_model, fr)
    position_dto = invoice_dto.positions[0]
    invoice_position = list(invoice.positions)[0]

    assert isinstance(position_dto, PublicationPositionImportDto)
    assert position_dto.type == "publication"
    assert position_dto.amount == invoice_position.cost.amount
    assert position_dto.tax_rate == invoice_position.tax_rate * 100
    assert position_dto.cost_type.value == invoice_position.item.cost_type.value
    assert position_dto.external_id == invoice_position.external_position_id


@pytest.mark.django_db
def test__contract_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    fr = create_funding_request(title="Test")
    contract = ContractDomainMapper.map(modelfactory.contract())
    contract_year = domainfactory.contract_year(contract)
    invoice = create_invoice_with_contract_position(contract_year)
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    position_model = invoice_model.positions.first()
    assert position_model is not None

    invoice_dto = map_invoice_to_dto(invoice_model, fr)
    position_dto = invoice_dto.positions[0]

    invoice_position = list(invoice.positions)[0]

    assert isinstance(position_dto, ContractPositionImportDto)
    assert position_dto.type == "contract"
    assert position_dto.amount == invoice_position.cost.amount
    assert position_dto.tax_rate == invoice_position.tax_rate * 100
    assert position_dto.cost_type == invoice_position.item.cost_type
    assert position_dto.external_id == invoice_position.external_position_id
    assert position_dto.contract_name == contract.name

    contract_item = invoice_position.item
    assert isinstance(contract_item, ContractItem)
    assert position_dto.contract_year == contract_item.item.year


@pytest.mark.django_db
def test__free_position__maps_to_dto__all_fields_are_mapped_correctly() -> None:
    fr = create_funding_request(title="Test")
    invoice = create_invoice_with_free_position()
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    invoice_dto = map_invoice_to_dto(invoice_model, fr)

    position_dto = invoice_dto.positions[0]
    invoice_position = list(invoice.positions)[0]

    assert isinstance(position_dto, FreePositionImportDto)
    assert position_dto.type == "free"
    assert position_dto.amount == invoice_position.cost.amount
    assert position_dto.tax_rate == invoice_position.tax_rate * 100
    assert position_dto.cost_type.value == invoice_position.item.cost_type.value
    assert position_dto.external_id == invoice_position.external_position_id
    assert position_dto.description == invoice_position.item.item


@pytest.mark.django_db
def test__invoice_with_position_and_funding_assignments__maps_to_dto__maps_assignments_correctly() -> (
    None
):
    fr = create_funding_request(title="Test")
    invoice = create_invoice_with_funding_assignments(
        fr,
        budget_amount=Decimal("1000.00"),
        institution_amount=Decimal("500.00"),
        cost_amount=Decimal("1500.00"),
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
    )
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))
    position = list(invoice.positions)[0]
    assert position is not None

    dto = map_invoice_to_dto(invoice_model, fr)

    position_dto = dto.positions[0]

    domain_fa = position.funding_assignments()[0]
    assert domain_fa.funding_source is not None
    domain_assignments = position.funding_assignments()

    first_domain_assignment = domain_assignments[0]
    assert first_domain_assignment.funding_source is not None
    assert position_dto.funding_assignments[0].name == first_domain_assignment.funding_source.name
    assert position_dto.funding_assignments[0].type == first_domain_assignment.funding_source.kind()
    assert position_dto.funding_assignments[0].amount == first_domain_assignment.amount.amount

    second_domain_assignment = domain_assignments[1]
    assert second_domain_assignment.funding_source is not None
    assert position_dto.funding_assignments[1].name == second_domain_assignment.funding_source.name
    assert (
        position_dto.funding_assignments[1].type == second_domain_assignment.funding_source.kind()
    )
    assert position_dto.funding_assignments[1].amount == second_domain_assignment.amount.amount


@pytest.mark.django_db
def test__invoice_with_multiple_positions__maps_to_dto__maps_all_positions_correctly() -> None:
    fr = create_funding_request(title="Test")
    invoice = create_invoice_with_mixed_positions(fr)
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    dto = map_invoice_to_dto(invoice_model, fr)

    assert len(dto.positions) == 3
    assert isinstance(dto.positions[0], PublicationPositionImportDto)
    assert isinstance(dto.positions[1], ContractPositionImportDto)
    assert isinstance(dto.positions[2], FreePositionImportDto)
