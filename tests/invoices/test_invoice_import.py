import tempfile
from decimal import Decimal
from typing import cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import importservice, repository
from coda.apps.invoices.importservice.dto import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    ConversionImportDto,
    FreePositionImportDto,
    InvoiceImportDto,
    InvoiceListImportDto,
    PublicationPositionImportDto,
)
from coda.apps.invoices.models import FundingSource
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.invoice import (
    AnyPosition,
    ContractCostType,
    ContractPosition,
    CreditorId,
    FundingSourceId,
    Invoice,
    PaymentStatus,
    Position,
    PublicationCostType,
    TaxRate,
)
from coda.domain.money import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


def publication_position_import_dto() -> PublicationPositionImportDto:
    fundingrequest = domainfactory.fundingrequest(
        journal_id=JournalId(modelfactory.journal().id),
        funding_org_id=FundingOrganizationId(modelfactory.funding_organization().id),
    )
    fundingrequest.id = fundingrequest_repository.create(fundingrequest)

    return PublicationPositionImportDto(
        type="publication",
        request_id=str(fundingrequest.request_id),
        legacy_request_id="legacy_request_id",
        tax_rate=Decimal("19.00"),
        amount=Decimal("100.00"),
        funding_source="publication-funding-source",
        external_id="external-publication-position",
        cost_type=PublicationCostType.Reprint.value,
    )


def contract_position_import_dto() -> ContractPositionImportDto:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)

    return ContractPositionImportDto(
        type="contract",
        contract_name=contract.name,
        contract_year=contract_year.year,
        tax_rate=Decimal("19.00"),
        amount=Decimal("200.00"),
        funding_source="contract-funding-source",
        external_id="external-contract-position",
        cost_type=ContractCostType.Read.value,
    )


def free_position_import_dto() -> FreePositionImportDto:
    return FreePositionImportDto(
        type="free",
        description="Free Position Description",
        tax_rate=Decimal("19.00"),
        amount=Decimal("50.00"),
        funding_source="free-position-funding-source",
        external_id="external-free-position",
        cost_type=PublicationCostType.Other.value,
    )


def invoice_import_list_dto(positions: list[CommonPositionImportDto]) -> InvoiceListImportDto:
    return InvoiceListImportDto(
        invoices=[
            InvoiceImportDto(
                number="INV-001",
                date="2023-10-01",
                creditor="creditor-id",
                currency=Currency.BBD.code,
                status="unpaid",
                external_id="external-invoice-id",
                comment="Test invoice comment",
                conversion=ConversionImportDto(
                    target_currency=Currency.EUR.code,
                    exchange_rate=Decimal("5.00"),
                ),
                positions=positions,
            ),
        ]
    )


def expected_publication_position(import_dto: PublicationPositionImportDto) -> AnyPosition:
    funding_source = FundingSource.objects.get(name=import_dto.funding_source)
    request = fundingrequest_repository.get_by_request_id(
        PublicFundingRequestId.from_str(str(import_dto.request_id))
    )
    publication_id = cast(PublicationId, request.publication.id)
    return Position(
        item=publication_id,
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        funding_source=FundingSourceId(funding_source.id),
        external_position_id=import_dto.external_id,
        cost_type=PublicationCostType(import_dto.cost_type),
    )


def expected_contract_position(import_dto: ContractPositionImportDto) -> AnyPosition:
    funding_source = FundingSource.objects.get(name=import_dto.funding_source)
    contract = contract_repository.get_by_name(import_dto.contract_name)
    assert contract is not None, "Contract should have been created by import service"
    contract_year = contract.in_year(import_dto.contract_year)
    return ContractPosition(
        item=contract_year,
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        funding_source=FundingSourceId(funding_source.id),
        external_position_id=import_dto.external_id,
        cost_type=ContractCostType(import_dto.cost_type),
    )


def expected_free_position(import_dto: FreePositionImportDto) -> AnyPosition:
    funding_source = FundingSource.objects.get(name=import_dto.funding_source)
    description = import_dto.description
    return Position(
        item=description,
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        funding_source=FundingSourceId(funding_source.id),
        external_position_id=import_dto.external_id,
        cost_type=PublicationCostType(import_dto.cost_type),
    )


def expected_invoice(import_dto: InvoiceImportDto) -> Invoice:
    positions = [
        expected_publication_position(cast(PublicationPositionImportDto, import_dto.positions[0])),
        expected_contract_position(cast(ContractPositionImportDto, import_dto.positions[1])),
        expected_free_position(cast(FreePositionImportDto, import_dto.positions[2])),
    ]

    expected_invoice = Invoice.new(
        number=import_dto.number,
        date=import_dto.date,
        creditor=CreditorId(modelfactory.creditor().id),
        status=PaymentStatus.Unpaid,
        external_invoice_id="external-invoice-id",
        comment="Test invoice comment",
        positions=positions,
    )
    expected_invoice.add_conversion(Decimal("5.00"), Currency.EUR)
    return expected_invoice


@pytest.mark.django_db
def test__full_invoice__import__is_saved_to_database() -> None:
    publication_position = publication_position_import_dto()
    contract_position = contract_position_import_dto()
    free_position = free_position_import_dto()
    import_dto = invoice_import_list_dto(
        positions=[publication_position, contract_position, free_position]
    )

    with tempfile.TemporaryFile("w+", encoding="utf-8") as temp_file:
        temp_file.write(import_dto.model_dump_json())
        temp_file.seek(0)
        importservice.import_invoices(temp_file)

    expected = expected_invoice(import_dto.invoices[0])
    actual = repository.first()
    assert actual is not None, "Invoice should have been created by import service"
    assert_invoice_eq(expected, actual)


# def _parse_into_position_import_dto(position: AnyPosition) -> CommonPositionImportDto:
#     match position.item:
#         case PublicationId() as publication_id:
#             request = fundingrequest_repository.get_by_publication_id(publication_id)

#             return PublicationPositionImportDto(
#                 type="publication",
#                 request_id=request.request_id,
#                 amount=position.net(),
#                 tax_rate=position.tax_rate,
#                 funding_source=position.funding_source,
#                 external_id=position.external_position_id,
#                 cost_type=position.cost_type,
#             )
#         case ContractYear() as contract_year:
#             return ContractPositionImportDto(
#                 type="contract",
#                 contract_name=contract_year.contract.name,
#                 contract_year=contract_year.year,
#                 amount=position.net(),
#                 tax_rate=position.tax_rate,
#                 funding_source=position.funding_source,
#                 external_id=position.external_position_id,
#                 cost_type=position.cost_type,
#             )
#         case str(description):
#             return FreePositionImportDto(
#                 type="free",
#                 description=description,
#                 amount=position.net(),
#                 tax_rate=position.tax_rate,
#                 funding_source=position.funding_source,
#                 external_id=position.external_position_id,
#                 cost_type=position.cost_type,
#             )
