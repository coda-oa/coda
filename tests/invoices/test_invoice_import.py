import datetime
import io
import json
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any, cast

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
from coda.contexts.finance.services.invoice_import import (
    InvoiceImportDataError,
    InvoiceImportReport,
    import_invoices,
)
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract
from coda.domain.date import DateRange
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.funding_sources import Budget, SplitSource
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.domain.finance.invoice_positions import ContractItem, FreeItem, Position, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest, FundingOrganizationId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, PublicationId
from coda.domain.publication.payment import PublicationPayments
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory
from tests.invoices import payment_assertions
from tests.invoices.test_invoice_repository import assert_invoice_eq


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

    _ = modelfactory.budget(name=contract_position.funding_source)
    _ = modelfactory.creditor(name=import_dto.invoices[0].creditor)
    _ = create_contract_from(contract_position)

    _ = import_invoices_from_dto_json(import_dto)

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
    position_dto = split_free_position_dto(assignments, amount=Decimal(30))
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
    position_dto = split_free_position_dto(
        [
            FundingAssignmentImportDto(type="budget", name="split 1"),
            FundingAssignmentImportDto(type="budget", name="split 2"),
        ],
        amount=Decimal(30),
    )
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
    position_dto = split_free_position_dto(
        [
            FundingAssignmentImportDto(type="institution", name=institution_1.name),
            FundingAssignmentImportDto(type="institution", name=institution_2.name),
        ],
        amount=Decimal(30),
    )
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
def test__publication_position_without_request_id__import_invoices__returns_validation_error() -> (
    None
):
    base_dto = publication_position_import_dto(create_funding_request())
    invalid_request_ids: dict[str, None] = {"request_id": None, "legacy_request_id": None}
    invalid_position = base_dto.model_copy(update=invalid_request_ids)
    invoice = invoice_dto(number="INV-001").model_copy(update={"positions": [invalid_position]})

    actual = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert actual.valid_invoices == 0
    assert actual.invalid_invoices == 1
    assert "INV-001" in actual.invoices_with_errors()
    assert len(actual.errors) == 1
    assert "Either request_id or legacy_request_id must be provided." in actual.errors[0].reasons[0]
    assert len(repository.all()) == 0


@pytest.mark.django_db
def test__invalid_split_amount_in_invoice__import_invoices__returns_error_report() -> None:
    position_dto = split_free_position_dto(
        [
            FundingAssignmentImportDto(type="budget", name="split 1", amount=Decimal(20)),
            FundingAssignmentImportDto(type="budget", name="split 2", amount=Decimal(40)),
        ],
        amount=Decimal(30),
    )
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
    position_dto = split_free_position_dto(
        [FundingAssignmentImportDto(type="institution", name="does not exist")],
        amount=Decimal(30),
    )
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
    position_dto = split_free_position_dto(
        [
            FundingAssignmentImportDto(type="budget", name="valid budget"),
            FundingAssignmentImportDto(type="institution", name="does not exist"),
        ],
        amount=Decimal(30),
    )
    import_dto = invoice_import_list_dto([position_dto])

    _ = import_invoices_from_dto_json(import_dto)

    with pytest.raises(funding_source_repository.FundingSourceNotFound):
        _ = funding_source_repository.get_by_name("valid budget")


@pytest.mark.django_db
def test__multiple_invalid_invoices__import_invoices__returns_errors_per_invoice() -> None:
    invalid_data: Any = {
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
    invalid_data: Any = {
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


def paid_invoice_dto_for_fundingrequest(fr: AnyFundingRequest) -> InvoiceImportDto:
    return paid_invoice_dto(
        number="INV-2025-002",
        positions=[publication_position_import_dto(fr)],
    )


PaidInvoicePaymentFixture = (
    paid_invoice_dto_for_fundingrequest,
    payment_assertions.new_invoice_paid_assertion,
)


def invoice_dto_for_fundingrequest(fr: AnyFundingRequest) -> InvoiceImportDto:
    return invoice_dto(
        number="INV-2025-002",
        positions=[publication_position_import_dto(fr)],
    )


UnpaidInvoicePaymentFixture = (
    invoice_dto_for_fundingrequest,
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

    publication_id = cast(PublicationId, funding_request.publication.id)
    payment_status = publications.get_payment_status(publication_id)
    imported_invoice = repository.first()

    assert imported_invoice is not None

    assert_payment_status = create_payments_assertion(imported_invoice)
    assert isinstance(payment_status, PublicationPayments)
    assert_payment_status(payment_status)


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__is_not_imported() -> None:
    position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="test-budget",
                amount=Decimal(50),
            )
        ]
    )

    invoice = invoice_dto(positions=[position])
    invoice.status = PaymentStatus.Paid
    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [invoice.number]


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__does_not_create_its_creditor_or_budget() -> None:
    position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="orphan-budget",
                amount=Decimal(50),
            )
        ]
    )

    invoice = invoice_dto(number="INV-ORPHAN", positions=[position])
    invoice.creditor = "orphan-creditor"
    invoice.status = PaymentStatus.Paid

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [invoice.number]
    assert repository.first() is None
    assert not Creditor.objects.filter(name="orphan-creditor").exists()
    assert not FundingSource.objects.filter(name="orphan-budget").exists()


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__does_not_create_its_contract() -> None:
    contract_position = contract_position_import_dto()
    unassigned_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="orphan-budget",
                amount=Decimal(50),
            )
        ]
    )

    invoice = invoice_dto(
        number="INV-ORPHAN-CONTRACT",
        positions=[contract_position, unassigned_position],
    )
    invoice.status = PaymentStatus.Paid

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [invoice.number]
    assert repository.first() is None
    assert not FundingSource.objects.filter(name="orphan-budget").exists()
    assert contract_repository.get_by_name(contract_position.contract_name) is None


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__keeps_creditor_needed_by_valid_invoice() -> None:
    rejected = invoice_with_budget_assignment(
        number="INV-REJECTED",
        creditor="shared-creditor",
        budget="orphan-budget",
        assigned_amount=Decimal(50),
        status=PaymentStatus.Paid,
    )
    valid = invoice_with_budget_assignment(
        number="INV-VALID",
        creditor="shared-creditor",
        budget="valid-budget",
        assigned_amount=Decimal(100),
    )

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[rejected, valid]))

    assert results.valid_invoices == 1
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [rejected.number]
    assert [invoice.number for invoice in repository.all()] == [valid.number]
    assert Creditor.objects.filter(name="shared-creditor").exists()
    assert not FundingSource.objects.filter(name="orphan-budget").exists()


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__keeps_budget_needed_by_valid_invoice() -> None:
    rejected = invoice_with_budget_assignment(
        number="INV-REJECTED",
        creditor="orphan-creditor",
        budget="shared-budget",
        assigned_amount=Decimal(50),
        status=PaymentStatus.Paid,
    )
    valid = invoice_with_budget_assignment(
        number="INV-VALID",
        creditor="valid-creditor",
        budget="shared-budget",
        assigned_amount=Decimal(100),
    )

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[rejected, valid]))

    assert results.valid_invoices == 1
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [rejected.number]
    assert [invoice.number for invoice in repository.all()] == [valid.number]
    assert not Creditor.objects.filter(name="orphan-creditor").exists()
    assert FundingSource.objects.filter(name="shared-budget").exists()


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__keeps_contract_needed_by_valid_invoice() -> None:
    contract_position = contract_position_import_dto()
    unassigned_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="orphan-budget",
                amount=Decimal(50),
            )
        ]
    )

    rejected = invoice_dto(
        number="INV-REJECTED",
        positions=[contract_position, unassigned_position],
    )
    rejected.creditor = "orphan-creditor"
    rejected.status = PaymentStatus.Paid

    valid = invoice_dto(number="INV-VALID", positions=[contract_position])
    valid.creditor = "valid-creditor"

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[rejected, valid]))

    assert results.valid_invoices == 1
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [rejected.number]
    assert [invoice.number for invoice in repository.all()] == [valid.number]
    assert contract_repository.get_by_name(contract_position.contract_name) is not None
    assert not Creditor.objects.filter(name="orphan-creditor").exists()
    assert not FundingSource.objects.filter(name="orphan-budget").exists()


@pytest.mark.django_db
def test__paid_invoice_with_unassigned_costs__keeps_pre_existing_entities() -> None:
    _ = modelfactory.creditor(name="pre-existing-creditor")
    _ = modelfactory.budget(name="pre-existing-budget")
    contract_position = contract_position_import_dto()
    _ = create_contract_from(contract_position)

    unassigned_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="pre-existing-budget",
                amount=Decimal(50),
            )
        ]
    )

    invoice = invoice_dto(
        number="INV-REJECTED",
        positions=[contract_position, unassigned_position],
    )
    invoice.creditor = "pre-existing-creditor"
    invoice.status = PaymentStatus.Paid

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert repository.first() is None
    assert Creditor.objects.filter(name="pre-existing-creditor").exists()
    assert funding_source_repository.get_by_name("pre-existing-budget") is not None
    assert contract_repository.get_by_name(contract_position.contract_name) is not None


@pytest.mark.django_db
def test__legacy_funding_source_name_matching_institution_source__is_imported_as_budget() -> None:
    institution = modelfactory.institution()
    _ = funding_source_repository.create(
        SplitSource.new(InstitutionId(institution.pk), "legacy-funding-source")
    )
    position = free_position_import_dto()
    position.funding_source = "legacy-funding-source"
    invoice = invoice_dto(number="INV-LEGACY", positions=[position])

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    imported = repository.first()
    assert imported is not None
    imported_position = next(iter(imported.positions))
    funding = next(iter(imported_position.funding_assignments())).funding_source
    funding_source_model = FundingSource.objects.get(name="legacy-funding-source", type="budget")
    assert results.valid_invoices == 1
    assert isinstance(funding, Budget)
    assert funding.id == FundingSourceId(funding_source_model.pk)


@pytest.mark.django_db
def test__position_with_funding_source_and_funding_assignments__import_invoices__rejects_invoice() -> (
    None
):
    contradicting_assignments = {
        "funding_source": "legacy-budget",
        "funding_assignments": [
            FundingAssignmentImportDto(type="budget", name="split-budget", amount=Decimal(100))
        ],
    }
    invalid_position = free_position_import_dto().model_copy(update=contradicting_assignments)
    invoice = invoice_dto(number="INV-CONFLICT")
    invoice = invoice.model_copy(update={"positions": [invalid_position]})

    report = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert report.valid_invoices == 0
    assert report.invalid_invoices == 1
    assert len(report.errors) == 1
    assert (
        "Use either funding_source or funding_assignments, not both." in report.errors[0].reasons[0]
    )
    assert FundingSource.objects.count() == 0
    assert Creditor.objects.count() == 0
    assert len(repository.all()) == 0


@pytest.mark.django_db
def test__assignment_name_collision_between_budget_and_institution__resolves_by_declared_type() -> (
    None
):
    institution = modelfactory.institution()
    institution.name = "collision-name"
    institution.save(update_fields=["name"])

    institution_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="institution",
                name="collision-name",
                amount=Decimal(100),
            )
        ]
    )

    budget_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="collision-name",
                amount=Decimal(100),
            )
        ]
    )

    invoice = invoice_dto(number="INV-COLLISION", positions=[institution_position, budget_position])

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 1
    imported = repository.first()
    assert imported is not None
    funding_by_kind = {
        assignment.funding_source.kind(): assignment.funding_source
        for position in imported.positions
        for assignment in position.funding_assignments()
        if assignment.funding_source is not None
    }
    institution_funding = funding_by_kind["institution"]
    budget_funding = funding_by_kind["budget"]
    assert isinstance(institution_funding, SplitSource)
    assert institution_funding.institution == InstitutionId(institution.pk)
    assert isinstance(budget_funding, Budget)
    assert budget_funding.name == "collision-name"

    institution_source = FundingSource.objects.get(name="collision-name", type="institution")
    budget_source = FundingSource.objects.get(name="collision-name", type="budget")
    assert institution_funding.id == FundingSourceId(institution_source.pk)
    assert budget_funding.id == FundingSourceId(budget_source.pk)


@pytest.mark.django_db
def test__invoice_with_over_allocated_assignment__does_not_create_creditor_or_budget() -> None:
    position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="orphan-budget",
                amount=Decimal(150),
            )
        ]
    )

    invoice = invoice_dto(number="INV-INVALID-SPLIT", positions=[position])
    invoice.creditor = "orphan-creditor"

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [invoice.number]
    assert repository.first() is None
    assert not Creditor.objects.filter(name="orphan-creditor").exists()
    assert not FundingSource.objects.filter(name="orphan-budget").exists()


@pytest.mark.django_db
def test__identical_invoices_with_invalid_position__report_one_error_each() -> None:
    position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name="orphan-budget",
                amount=Decimal(150),
            )
        ]
    )
    invoice = invoice_dto(number="INV-DUPLICATE", positions=[position])

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice, invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert len(results.errors) == 2
    assert results.invoices_with_errors() == [invoice.number, invoice.number]


@pytest.mark.django_db
def test__invoice_with_two_reasons__counts_as_one_invalid_invoice() -> None:
    publication_position = non_existing_publication_position_import_dto()
    institution_position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="institution",
                name="non-existing-institution",
                amount=Decimal(100),
            )
        ]
    )

    invoice = invoice_dto(
        number="INV-MULTI",
        positions=[publication_position, institution_position],
    )

    results = import_invoices_from_dto_json(InvoiceListImportDto(invoices=[invoice]))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert len(results.errors) == 2
    assert {error.invoice_number for error in results.errors} == {invoice.number}


@pytest.mark.django_db
def test__one_valid_and_one_malformed_invoice__imports_valid_invoice() -> None:
    valid_invoice = invoice_dto()
    invalid_invoice = invoice_dto().model_copy(update={"currency": "invalid"})

    results = import_invoices_from_dto_json(
        InvoiceListImportDto(invoices=[invalid_invoice, valid_invoice])
    )

    assert results.valid_invoices == 1
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == [invalid_invoice.number]
    assert repository.first() is not None


@pytest.mark.parametrize(
    ("json_content", "expected_reason"),
    [
        ("{}", "invoices: Field required"),
        (f'{{"typo": [ {invoice_dto().model_dump_json()} ]}}', "invoices: Field required"),
        ('{"invoices": "not-a-list"}', "invoices: Input should be a valid list"),
        ('{"invoices": null}', "invoices: Input should be a valid list"),
        ("[]", "Import file must contain a JSON object"),
        ('{"invoices": ', "Invalid JSON"),
    ],
)
def test__invalid_import_document__raises_data_error(
    json_content: str, expected_reason: str
) -> None:
    with pytest.raises(InvoiceImportDataError) as exc_info:
        import_invoices(io.StringIO(json_content))

    assert expected_reason in "; ".join(exc_info.value.reasons)


@pytest.mark.django_db
def test__invoice_json_is_not_an_object__is_not_imported() -> None:
    json_content = json.dumps({"invoices": ["not-an-object"]})

    results = import_invoices(io.StringIO(json_content))

    assert results.valid_invoices == 0
    assert results.invalid_invoices == 1
    assert results.invoices_with_errors() == ["<unknown-0>"]


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


def split_free_position_dto(
    assignments: list[FundingAssignmentImportDto],
    amount: Decimal = Decimal(100),
) -> FreePositionImportDto:
    position = free_position_import_dto()
    position.amount = amount
    position.funding_source = ""
    position.funding_assignments = assignments
    return position


def invoice_import_list_dto(positions: list[CommonPositionImportDto]) -> InvoiceListImportDto:
    return InvoiceListImportDto(invoices=[invoice_dto(positions=positions)])


def paid_invoice_dto(
    number: str = "INV-001", positions: Iterable[CommonPositionImportDto] = ()
) -> InvoiceImportDto:
    dto = invoice_dto(number, positions)
    dto.status = PaymentStatus.Paid
    return dto


def invoice_with_budget_assignment(
    number: str,
    creditor: str,
    budget: str,
    assigned_amount: Decimal,
    status: PaymentStatus = PaymentStatus.Unpaid,
) -> InvoiceImportDto:
    position = split_free_position_dto(
        [
            FundingAssignmentImportDto(
                type="budget",
                name=budget,
                amount=assigned_amount,
            )
        ]
    )

    invoice = invoice_dto(number=number, positions=[position])
    invoice.creditor = creditor
    invoice.status = status
    return invoice


def expected_publication_position(import_dto: PublicationPositionImportDto) -> Position:
    funding_source = FundingSource.objects.filter(name=import_dto.funding_source).first()
    assert funding_source is not None, (
        f"FundingSource '{import_dto.funding_source}' should exist in the database"
    )
    request = fundingrequest_repository.get_by_request_id(
        PublicFundingRequestId.from_str(str(import_dto.request_id))
    )
    publication_id = cast(PublicationId, request.publication.id)
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
    assert funding_source is not None, (
        f"FundingSource '{import_dto.funding_source}' should exist in the database"
    )
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
