import datetime
import io
from collections.abc import Callable, Iterable
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
from coda.apps.invoices.models import Creditor, FundingSource
from coda.apps.publications.services import publications
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest, FundingOrganizationId
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
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, PublicationId
from coda.domain.publication.payment import (
    PublicationPayments,
)
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.invoices import payment_assertions
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
def test__full_invoice__import__is_saved_to_database() -> None:
    import_dto = invoice_import_list_dto(create_position_dtos())

    report = import_invoices(import_dto)

    expected = expected_invoice(import_dto.invoices[0])
    actual = repository.first()
    assert actual is not None, "Invoice should have been created by import service"
    assert_invoice_eq(expected, actual)
    assert report.valid_invoices == 1
    assert report.errors == {}


@pytest.mark.django_db
def test__full_invoice__related_entities_already_exist__is_not_created_again() -> None:
    contract_position = contract_position_import_dto()
    import_dto = invoice_import_list_dto([contract_position])

    modelfactory.funding_source(name=contract_position.funding_source)
    modelfactory.creditor(name=import_dto.invoices[0].creditor)
    create_contract_from(contract_position)

    import_invoices(import_dto)

    assert FundingSource.objects.count() == 1
    assert Creditor.objects.count() == 1
    assert len(contract_repository.all()) == 1


@pytest.mark.django_db
def test__one_invoice_with_non_existing_publication_position__import_invoices__still_imports_other_invoices() -> (
    None
):
    invalid_dto = invoice_dto(
        number="INV-001", positions=[non_existing_publication_position_import_dto()]
    )
    valid_dto = invoice_dto(number="INV-002", positions=create_position_dtos())

    actual = import_invoices(InvoiceListImportDto(invoices=[invalid_dto, valid_dto]))

    assert_valid_invoice_imported(valid_dto)
    assert actual.valid_invoices == 1
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.errors


@pytest.mark.django_db
def test__invoice_with_non_existing_publication_position__import_invoices__does_not_create_related_entities() -> (
    None
):
    invalid_dto = invoice_dto(
        number="INV-001", positions=[non_existing_publication_position_import_dto()]
    )

    _ = import_invoices(InvoiceListImportDto(invoices=[invalid_dto]))

    assert FundingSource.objects.count() == 0
    assert Creditor.objects.count() == 0
    assert len(repository.all()) == 0


@pytest.mark.django_db
def test__invalid_dto_data__import_invoices__returns_error_report() -> None:
    invalid_dto = InvoiceImportDto.model_construct(
        number="INV-001",
        date=datetime.date.today(),
        creditor="",
        currency="BBD",
        status=PaymentStatus.Unpaid,
        positions=[],
    )

    actual = import_invoices(InvoiceListImportDto(invoices=[invalid_dto]))

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.errors


@pytest.mark.django_db
def test__multiple_invalid_invoices__import_invoices__returns_errors_per_invoice() -> None:
    # Create invalid JSON data that will fail validation
    invalid_data = {
        "invoices": [
            {
                "number": "INV-001",
                "date": str(datetime.date.today()),
                "creditor": "",  # Invalid: empty string
                "currency": "BBD",
                "status": "unpaid",
                "positions": [],
            },
            {
                "number": "INV-002",
                "date": str(datetime.date.today()),
                "creditor": "Valid Creditor",
                "currency": "INVALID",  # Invalid: currency code
                "status": "unpaid",
                "positions": [],
            },
        ]
    }

    import io
    import json

    json_stream = io.StringIO(json.dumps(invalid_data))
    actual = importservice.import_invoices(json_stream)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 2
    assert "INV-001" in actual.errors
    assert "INV-002" in actual.errors
    assert len(actual.errors) == 2


@pytest.mark.django_db
def test__invoice_without_number__import_invoices__uses_fallback_key() -> None:
    # Create invalid JSON data without a number field
    invalid_data = {
        "invoices": [
            {
                # Missing "number" field
                "date": str(datetime.date.today()),
                "creditor": "Test Creditor",
                "currency": "EUR",
                "status": "unpaid",
                "positions": [],
            }
        ]
    }

    import io
    import json

    json_stream = io.StringIO(json.dumps(invalid_data))
    actual = importservice.import_invoices(json_stream)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "<unknown-0>" in actual.errors  # Fallback key when number is missing


PaidInvoicePaymentFixture = (
    lambda fr: paid_invoice_dto(
        number="INV-2025-001",
        positions=[publication_position_import_dto(fr)],
    ),
    payment_assertions.new_invoice_paid_assertion,
)


UnpaidInvoicePaymentFixture = (
    lambda fr: invoice_dto(
        number="INV-2025-002",
        positions=[publication_position_import_dto(fr)],
    ),
    payment_assertions.new_invoice_received_assertion,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "invoice_dto, create_payments_assertion",
    [PaidInvoicePaymentFixture, UnpaidInvoicePaymentFixture],
)
def test__unpaid_invoice_with_publication_position_import_invoices_funding_request_has_payment_status_invoice_received(
    invoice_dto: Callable[[AnyFundingRequest], InvoiceImportDto],
    create_payments_assertion: payment_assertions.CreatePaymentsAssertion,
) -> None:
    funding_request = create_funding_request()
    import_dto = InvoiceListImportDto(invoices=[invoice_dto(funding_request)])

    _ = import_invoices(import_dto)

    publication_id = cast(PublicationId, funding_request.publication.id)
    payment_status = publications.get_payment_status(publication_id)
    imported_invoice = repository.first()

    assert imported_invoice is not None

    assert_payment_status = create_payments_assertion(imported_invoice)
    assert isinstance(payment_status, PublicationPayments)
    assert_payment_status(payment_status)


def assert_valid_invoice_imported(valid_dto: InvoiceImportDto) -> None:
    all_invoices = repository.all()
    expected = expected_invoice(valid_dto)
    assert len(all_invoices) == 1
    actual = all_invoices[0]
    assert_invoice_eq(expected, actual)


def import_invoices(import_dto: InvoiceListImportDto) -> importservice.InvoiceImportReport:
    temp_stream = io.StringIO(import_dto.model_dump_json())
    return importservice.import_invoices(temp_stream)


def publication_position_import_dto(
    fundingrequest: AnyFundingRequest,
) -> PublicationPositionImportDto:
    request_id = str(fundingrequest.request_id)
    return PublicationPositionImportDto(
        request_id=request_id,
        legacy_request_id="legacy_request_id",
        tax_rate=Decimal("19.00"),
        amount=Decimal("100.00"),
        funding_source="publication-funding-source",
        external_id="external-publication-position",
        cost_type=PublicationCostType.Reprint.value,
    )


def non_existing_publication_position_import_dto() -> PublicationPositionImportDto:
    return PublicationPositionImportDto(
        legacy_request_id="non-existing-legacy-request-id",
        tax_rate=Decimal("19.00"),
        amount=Decimal("100.00"),
        cost_type=PublicationCostType.Gold_OA.value,
    )


def create_funding_request() -> AnyFundingRequest:
    fundingrequest = domainfactory.fundingrequest(
        journal_id=JournalId(modelfactory.journal().id),
        funding_org_id=FundingOrganizationId(modelfactory.funding_organization().id),
    )
    fundingrequest.id = fundingrequest_repository.create(fundingrequest)
    return fundingrequest


def contract_position_import_dto() -> ContractPositionImportDto:
    contract = domainfactory.contract()
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
    return InvoiceListImportDto(invoices=[invoice_dto(positions=positions)])


def invoice_dto(
    number: str = "INV-001", positions: Iterable[CommonPositionImportDto] = ()
) -> InvoiceImportDto:
    return InvoiceImportDto(
        number=number,
        date="2023-10-01",
        creditor="creditor-name",
        currency=Currency.BBD.code,
        status="unpaid",
        external_id="external-invoice-id",
        comment="Test invoice comment",
        conversion=ConversionImportDto(
            target_currency=Currency.EUR.code,
            exchange_rate=Decimal("5.00"),
        ),
        positions=positions,
    )


def paid_invoice_dto(
    number: str = "INV-001", positions: Iterable[CommonPositionImportDto] = ()
) -> InvoiceImportDto:
    dto = invoice_dto(number, positions)
    dto.status = PaymentStatus.Paid
    return dto


def expected_publication_position(import_dto: PublicationPositionImportDto) -> AnyPosition:
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert (
        funding_source is not None
    ), f"FundingSource '{import_dto.funding_source}' should exist in the database"
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
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert funding_source is not None, f"FundingSource '{import_dto.funding_source}' should exist"

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
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert (
        funding_source is not None
    ), f"FundingSource '{import_dto.funding_source}' should exist in the database"
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

    creditor = Creditor.objects.filter(name=import_dto.creditor).first()
    assert creditor is not None, "Creditor should have been created by import service"

    expected_invoice = Invoice.new(
        number=import_dto.number,
        date=import_dto.date,
        creditor=CreditorId(creditor.id),
        status=PaymentStatus.Unpaid,
        external_invoice_id="external-invoice-id",
        comment="Test invoice comment",
        positions=positions,
    )
    expected_invoice.add_conversion(Decimal("5.00"), Currency.EUR)
    return expected_invoice


def create_position_dtos() -> list[CommonPositionImportDto]:
    return [
        publication_position_import_dto(create_funding_request()),
        contract_position_import_dto(),
        free_position_import_dto(),
    ]


def create_contract_from(contract_position: ContractPositionImportDto) -> Contract:
    contract = Contract.new(
        name=NonEmptyStr(contract_position.contract_name),
        period=complete_year(contract_position.contract_year),
    )
    contract.id = contract_repository.create(contract)
    return contract


def complete_year(year: int) -> DateRange:
    return DateRange.create(start=datetime.date(year, 1, 1), end=datetime.date(year, 12, 31))
