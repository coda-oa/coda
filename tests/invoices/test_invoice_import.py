import datetime
import io
import json
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import funding_source_repository, invoice_query, repository
from coda.apps.invoices.models import Creditor, FundingSource
from coda.apps.publications.services import publications
from coda.contexts.finance.dto.import_dtos import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    ConversionImportDto,
    FreePositionImportDto,
    FundingAssignmentImportDto,
    InvoiceImportDto,
    InvoiceListImportDto,
    PublicationPositionImportDto,
)
from coda.contexts.finance.services.invoice_import import InvoiceImportReport, import_invoices
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.domain.finance.invoice_positions import ContractItem, FreeItem, Position, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest, FundingOrganizationId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId
from coda.domain.publication.payment import PublicationPayments
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.invoices import payment_assertions
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
def test__full_invoice__import__is_saved_to_database() -> None:
    import_dto = invoice_import_list_dto(create_position_dtos())

    report = import_invoices_from_dto_json(import_dto)

    expected = expected_full_invoice(import_dto.invoices[0])
    actual = repository.first()
    assert actual is not None, "Invoice should have been created by import service"
    assert_invoice_eq(expected, actual)
    assert report.valid_invoices == 1
    assert report.errors == []


@pytest.mark.django_db
def test__full_invoice__related_entities_already_exist__is_not_created_again() -> None:
    contract_position = contract_position_import_dto()
    import_dto = invoice_import_list_dto([contract_position])

    modelfactory.budget(name=contract_position.funding_source)
    modelfactory.creditor(name=import_dto.invoices[0].creditor)
    create_contract_from(contract_position)

    import_invoices_from_dto_json(import_dto)

    assert FundingSource.objects.count() == 1
    assert Creditor.objects.count() == 1
    assert len(contract_repository.all()) == 1


@pytest.mark.django_db
def test__multiple_invoices_with_different_currencies__import__each_keeps_correct_currency() -> (
    None
):
    """Regression test: invoices with different currencies must retain their original currency."""
    eur_position = free_position_import_dto()
    eur_position.amount = Decimal("100.00")

    usd_position = free_position_import_dto()
    usd_position.amount = Decimal("200.00")

    chf_position = free_position_import_dto()
    chf_position.amount = Decimal("300.00")

    eur_invoice = InvoiceImportDto(
        number="EUR-001",
        date=datetime.date(2023, 1, 1),
        creditor="Test Creditor",
        currency="EUR",
        status=PaymentStatus.Unpaid,
        positions=[eur_position],
    )

    usd_invoice = InvoiceImportDto(
        number="USD-002",
        date=datetime.date(2023, 1, 2),
        creditor="Test Creditor",
        currency="USD",
        status=PaymentStatus.Unpaid,
        conversion=ConversionImportDto(
            target_currency="EUR",
            exchange_rate=Decimal("0.85"),
        ),
        positions=[usd_position],
    )

    chf_invoice = InvoiceImportDto(
        number="CHF-003",
        date=datetime.date(2023, 1, 3),
        creditor="Test Creditor",
        currency="CHF",
        status=PaymentStatus.Unpaid,
        conversion=ConversionImportDto(
            target_currency="EUR",
            exchange_rate=Decimal("0.95"),
        ),
        positions=[chf_position],
    )

    import_dto = InvoiceListImportDto(invoices=[eur_invoice, usd_invoice, chf_invoice])

    _ = import_invoices_from_dto_json(import_dto)

    saved_invoices = repository.all()
    invoice_by_number = {inv.number: inv for inv in saved_invoices}

    eur_saved = invoice_by_number["EUR-001"]
    usd_saved = invoice_by_number["USD-002"]
    chf_saved = invoice_by_number["CHF-003"]

    assert eur_saved.currency() == Currency.EUR
    assert usd_saved.currency() == Currency.USD
    assert chf_saved.currency() == Currency.CHF


@pytest.mark.django_db
@pytest.mark.parametrize(
    "assignments",
    [
        [
            FundingAssignmentImportDto(type="budget", name="split 1", amount=Decimal(10)),
            FundingAssignmentImportDto(type="budget", name="split 2", amount=Decimal(20)),
        ],
        [
            FundingAssignmentImportDto(type="budget", name="split 1"),
            FundingAssignmentImportDto(type="budget", name="split 2", amount=Decimal(20)),
        ],
    ],
    ids=["explicit assignments", "partial explicit assignments"],
)
def test__invoice_with_split_position_with_explicit_assignments__import_invoice__imports_with_splits(
    assignments: list[FundingAssignmentImportDto],
) -> None:
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = assignments
    import_dto = invoice_import_list_dto([position_dto])

    _ = import_invoices_from_dto_json(import_dto)

    invoice_dto = import_dto.invoices[0]
    expected = expected_invoice_head(invoice_dto)
    position = invoice_positions.create(
        item=FreeItem(position_dto.description, cost_type=position_dto.cost_type),
        cost=Money(30, Currency.from_code(invoice_dto.currency)),
        tax_rate=TaxRate.from_percentage(position_dto.tax_rate),
        external_position_id=position_dto.external_id,
    )

    split_1 = funding_source_repository.get_by_name("split 1")
    split_2 = funding_source_repository.get_by_name("split 2")
    position.assign_funding(split_1, Decimal(10))
    position.assign_funding(split_2, Decimal(20))

    expected.positions = [position]
    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
def test__invoice_with_split_position_with_implicit_assignments__import_invoice__imports_with_splits() -> (
    None
):
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = [
        FundingAssignmentImportDto(type="budget", name="split 1"),
        FundingAssignmentImportDto(type="budget", name="split 2"),
    ]
    import_dto = invoice_import_list_dto([position_dto])

    _ = import_invoices_from_dto_json(import_dto)

    invoice_dto = import_dto.invoices[0]
    expected = expected_invoice_head(invoice_dto)
    position = invoice_positions.create(
        item=FreeItem(position_dto.description, cost_type=position_dto.cost_type),
        cost=Money(30, Currency.from_code(invoice_dto.currency)),
        tax_rate=TaxRate.from_percentage(position_dto.tax_rate),
        external_position_id=position_dto.external_id,
    )

    split_1 = funding_source_repository.get_by_name("split 1")
    split_2 = funding_source_repository.get_by_name("split 2")
    position.assign_funding(split_1, Decimal(15))
    position.assign_funding(split_2, Decimal(15))

    expected.positions = [position]
    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
def test__invoice_with_split_institution_position__import_invoices__creates_institution_source_on_import() -> (
    None
):
    institution_1 = modelfactory.institution()
    institution_2 = modelfactory.institution()
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = [
        FundingAssignmentImportDto(type="institution", name=institution_1.name),
        FundingAssignmentImportDto(type="institution", name=institution_2.name),
    ]
    import_dto = invoice_import_list_dto([position_dto])

    _ = import_invoices_from_dto_json(import_dto)

    invoice_dto = import_dto.invoices[0]
    expected = expected_invoice_head(invoice_dto)
    position = invoice_positions.create(
        item=FreeItem(position_dto.description, cost_type=position_dto.cost_type),
        cost=Money(30, Currency.from_code(invoice_dto.currency)),
        tax_rate=TaxRate.from_percentage(position_dto.tax_rate),
        external_position_id=position_dto.external_id,
    )

    split_1 = funding_source_repository.get_by_institution(InstitutionId(institution_1.pk))
    split_2 = funding_source_repository.get_by_institution(InstitutionId(institution_2.pk))
    position.assign_funding(split_1, Decimal(15))
    position.assign_funding(split_2, Decimal(15))

    expected.positions = [position]
    actual = repository.first()
    assert actual is not None
    assert_invoice_eq(expected, actual)


@pytest.mark.django_db
def test__invoice_with_non_existing_publication_position__import_invoices__does_not_import_invoice() -> (
    None
):
    invalid_dto = invoice_dto(
        number="INV-001", positions=[non_existing_publication_position_import_dto()]
    )

    actual = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invalid_dto]))

    assert "INV-001" in actual.invoices_with_errors()
    assert actual.valid_invoices == 0
    assert len(invoice_query.search(invoice_query.GenericSearchCriterion("INV-001"))) == 0


@pytest.mark.django_db
def test__one_invoice_with_non_existing_publication_position__import_invoices__still_imports_other_invoices() -> (
    None
):
    invalid_dto = invoice_dto(
        number="INV-001", positions=[non_existing_publication_position_import_dto()]
    )
    valid_dto = invoice_dto(number="INV-002", positions=create_position_dtos())

    actual = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invalid_dto, valid_dto]))

    assert_valid_invoice_imported(valid_dto)
    assert actual.valid_invoices == 1
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.invoices_with_errors()


@pytest.mark.django_db
def test__invoice_with_non_existing_publication_position__import_invoices__does_not_create_related_entities() -> (
    None
):
    invalid_dto = invoice_dto(
        number="INV-001", positions=[non_existing_publication_position_import_dto()]
    )

    _ = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invalid_dto]))

    assert FundingSource.objects.count() == 0
    assert Creditor.objects.count() == 0
    assert len(repository.all()) == 0


@pytest.mark.django_db
def test__invalid_invoice_head_data__import_invoices__returns_error_report() -> None:
    invalid_dto = InvoiceImportDto.model_construct(
        number="INV-001",
        date=datetime.date.today(),
        creditor="",
        currency="BBD",
        status=PaymentStatus.Unpaid,
        positions=[],
    )

    actual = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invalid_dto]))

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.invoices_with_errors()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "request_id",
    ("20241215-ABCD1234", "coda-20241215-ABCD1234", "coda-20241215-ABCD12341234"),
    ids=("invalid format", "too short", "non existing request id"),
)
def test__publication_position_with_invalid_request_id__import_invoices__returns_validation_error(
    request_id: str,
) -> None:
    """
    Regression test: A publication position with an invalid request_id format or non existing publication
    should raise a validation error, not be silently converted to a free position.
    """
    invalid_data = {
        "invoices": [
            {
                "number": "INV-001",
                "date": "2024-12-15",
                "creditor": "Test Creditor",
                "currency": "EUR",
                "status": "unpaid",
                "positions": [
                    {
                        "type": "publication",
                        "amount": 2000.00,
                        "tax_rate": 19.00,
                        "cost_type": "gold-oa",
                        "request_id": request_id,
                    }
                ],
            }
        ]
    }

    json_stream = io.StringIO(json.dumps(invalid_data))
    actual = import_invoices(json_stream)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.invoices_with_errors()
    assert len(repository.all()) == 0


@pytest.mark.django_db
def test__invalid_split_amount_in_invoice__import_invoices__returns_error_report() -> None:
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = [
        FundingAssignmentImportDto(type="budget", name="split 1", amount=Decimal(20)),
        FundingAssignmentImportDto(type="budget", name="split 2", amount=Decimal(40)),
    ]
    import_dto = invoice_import_list_dto([position_dto])
    invoice_dto = import_dto.invoices[0]

    actual = import_invoices_from_dto_json(import_dto)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert invoice_dto.number in actual.invoices_with_errors()


@pytest.mark.django_db
def test__non_existing_institution_in_invoice_position__import_invoices__returns_error_report() -> (
    None
):
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = [
        FundingAssignmentImportDto(type="institution", name="does not exist")
    ]
    import_dto = invoice_import_list_dto([position_dto])
    invoice_dto = import_dto.invoices[0]

    actual = import_invoices_from_dto_json(import_dto)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert invoice_dto.number in actual.invoices_with_errors()


@pytest.mark.django_db
def test__invoice_with_budget_and_non_existing_institution__import_invoices__does_not_create_budget() -> (
    None
):
    position_dto = free_position_import_dto()
    position_dto.funding_source = ""
    position_dto.amount = Decimal(30)
    position_dto.funding_assignments = [
        FundingAssignmentImportDto(type="budget", name="valid budget"),
        FundingAssignmentImportDto(type="institution", name="does not exist"),
    ]
    import_dto = invoice_import_list_dto([position_dto])

    _ = import_invoices_from_dto_json(import_dto)

    with pytest.raises(funding_source_repository.FundingSourceNotFound):
        funding_source_repository.get_by_name("valid budget")


@pytest.mark.django_db
def test__multiple_invalid_invoices__import_invoices__returns_errors_per_invoice() -> None:
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

    json_stream = io.StringIO(json.dumps(invalid_data))
    actual = import_invoices(json_stream)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 2
    assert "INV-001" in actual.invoices_with_errors()
    assert "INV-002" in actual.invoices_with_errors()
    assert len(actual.errors) == 2


@pytest.mark.django_db
def test__invoice_without_number__import_invoices__uses_fallback_key() -> None:
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

    json_stream = io.StringIO(json.dumps(invalid_data))
    actual = import_invoices(json_stream)

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "<unknown-0>" in actual.invoices_with_errors()


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

    _ = import_invoices_from_dto_json(import_dto)

    publication_id = funding_request.publication.id
    payment_status = publications.get_payment_status(publication_id)
    imported_invoice = repository.first()

    assert imported_invoice is not None

    assert_payment_status = create_payments_assertion(imported_invoice)
    assert isinstance(payment_status, PublicationPayments)
    assert_payment_status(payment_status)


def assert_valid_invoice_imported(valid_dto: InvoiceImportDto) -> None:
    all_invoices = repository.all()
    expected = expected_full_invoice(valid_dto)
    assert len(all_invoices) == 1
    actual = all_invoices[0]
    assert_invoice_eq(expected, actual)


def import_invoices_from_dto_json(import_dto: InvoiceListImportDto) -> InvoiceImportReport:
    temp_stream = io.StringIO(import_dto.model_dump_json())
    return import_invoices(temp_stream)


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
        cost_type=PublicationCostType.Reprint,
    )


def non_existing_publication_position_import_dto() -> PublicationPositionImportDto:
    return PublicationPositionImportDto(
        legacy_request_id="non-existing-legacy-request-id",
        tax_rate=Decimal("19.00"),
        amount=Decimal("100.00"),
        cost_type=PublicationCostType.Gold_OA,
    )


def create_funding_request() -> AnyFundingRequest:
    fundingrequest = domainfactory.fundingrequest(
        journal_id=JournalId(modelfactory.journal().pk),
        funding_org_id=FundingOrganizationId(modelfactory.funding_organization().pk),
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
        cost_type=ContractCostType.Read,
    )


def free_position_import_dto() -> FreePositionImportDto:
    return FreePositionImportDto(
        type="free",
        description="Free Position Description",
        tax_rate=Decimal("19.00"),
        amount=Decimal("50.00"),
        funding_source="free-position-funding-source",
        external_id="external-free-position",
        cost_type=PublicationCostType.Other,
    )


def invoice_import_list_dto(positions: list[CommonPositionImportDto]) -> InvoiceListImportDto:
    return InvoiceListImportDto(invoices=[invoice_dto(positions=positions)])


def invoice_dto(
    number: str = "INV-001", positions: Iterable[CommonPositionImportDto] = ()
) -> InvoiceImportDto:
    return InvoiceImportDto(
        number=number,
        date=datetime.date(2023, 10, 1),
        creditor="creditor-name",
        currency=Currency.BBD.code,
        status=PaymentStatus.Unpaid,
        external_id="external-invoice-id",
        comment="Test invoice comment",
        conversion=ConversionImportDto(
            target_currency=Currency.EUR.code,
            exchange_rate=Decimal("5.00"),
        ),
        positions=list(positions),
    )


def paid_invoice_dto(
    number: str = "INV-001", positions: Iterable[CommonPositionImportDto] = ()
) -> InvoiceImportDto:
    dto = invoice_dto(number, positions)
    dto.status = PaymentStatus.Paid
    return dto


def expected_publication_position(import_dto: PublicationPositionImportDto) -> Position:
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert (
        funding_source is not None
    ), f"FundingSource '{import_dto.funding_source}' should exist in the database"
    request = fundingrequest_repository.get_by_request_id(
        PublicFundingRequestId.from_str(str(import_dto.request_id))
    )
    publication_id = request.publication.id
    position = invoice_positions.create(
        item=PublicationItem(
            publication_id,
            cost_type=PublicationCostType(import_dto.cost_type),
        ),
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        external_position_id=import_dto.external_id,
    )

    budget = Budget(FundingSourceId(funding_source.pk), funding_source.name)
    position.assign_remaining(budget)
    return position


def expected_contract_position(import_dto: ContractPositionImportDto) -> Position:
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert funding_source is not None, f"FundingSource '{import_dto.funding_source}' should exist"

    contract = contract_repository.get_by_name(import_dto.contract_name)
    assert contract is not None, "Contract should have been created by import service"

    contract_year = contract.in_year(import_dto.contract_year)
    position = invoice_positions.create(
        item=ContractItem(
            contract_year,
            cost_type=ContractCostType(import_dto.cost_type),
        ),
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        external_position_id=import_dto.external_id,
    )
    budget = Budget(FundingSourceId(funding_source.pk), funding_source.name)
    position.assign_remaining(budget)
    return position


def expected_free_position(import_dto: FreePositionImportDto) -> Position:
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert (
        funding_source is not None
    ), f"FundingSource '{import_dto.funding_source}' should exist in the database"
    description = import_dto.description
    position = invoice_positions.create(
        item=FreeItem(
            description,
            cost_type=PublicationCostType(import_dto.cost_type),
        ),
        cost=Money(import_dto.amount, Currency.BBD),
        tax_rate=TaxRate.from_percentage(import_dto.tax_rate),
        external_position_id=import_dto.external_id,
    )
    budget = Budget(FundingSourceId(funding_source.pk), funding_source.name)
    position.assign_remaining(budget)
    return position


def expected_full_invoice(import_dto: InvoiceImportDto) -> Invoice:
    positions = [
        expected_publication_position(cast(PublicationPositionImportDto, import_dto.positions[0])),
        expected_contract_position(cast(ContractPositionImportDto, import_dto.positions[1])),
        expected_free_position(cast(FreePositionImportDto, import_dto.positions[2])),
    ]

    creditor = Creditor.objects.filter(name=import_dto.creditor).first()
    assert creditor is not None, "Creditor should have been created by import service"

    expected_invoice = expected_invoice_head(import_dto)
    expected_invoice.positions = positions
    return expected_invoice


def expected_invoice_head(import_dto: InvoiceImportDto) -> Invoice:
    creditor = Creditor.objects.filter(name=import_dto.creditor).first()
    assert creditor is not None, "Creditor should have been created by import service"

    invoice = Invoice.new(
        number=import_dto.number,
        date=import_dto.date,
        creditor=CreditorId(creditor.pk),
        status=PaymentStatus.Unpaid,
        external_invoice_id="external-invoice-id",
        comment="Test invoice comment",
        positions=[],
    )
    invoice.add_conversion(Decimal("5.00"), Currency.EUR)
    return invoice


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
