from decimal import Decimal
from typing import cast

import faker
import pytest

from coda.apps.contracts import repository as contract_services
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import funding_source_repository, repository
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract, ContractYear, PublisherId
from coda.domain.date import DateRange
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import CreditorId, Invoice, PaymentStatus
from coda.domain.finance.invoice_positions import Position
from coda.domain.fundingrequest import FundingOrganizationId
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory

_faker = faker.Faker()


@pytest.mark.django_db
def test__save_new_invoice__saves_invoice_to_database() -> None:
    invoice = full_invoice()

    new_id = repository.create(invoice)

    actual = repository.get_by_id(new_id)
    assert_invoice_eq(invoice, actual)


@pytest.mark.django_db
def test__given_saved_invoice__create_again__raises_error() -> None:
    invoice = full_invoice()
    invoice.id = repository.create(invoice)

    with pytest.raises(repository.InvoiceAlreadyExists):
        repository.create(invoice)


@pytest.mark.django_db
def test__given_updated_invoice__save__updates_invoice_in_database() -> None:
    invoice = full_invoice()
    invoice.status = PaymentStatus.Unpaid

    new_id = repository.create(invoice)

    updated_invoice = repository.get_by_id(new_id)
    updated_invoice.number = "updated"
    updated_invoice.creditor = CreditorId(modelfactory.creditor().pk)
    updated_invoice.status = PaymentStatus.Paid
    updated_invoice.date = _faker.date_object()
    updated_invoice.positions = [domainfactory.free_position()]
    updated_invoice.comment = "updated"
    updated_invoice.external_invoice_id = "updated"

    updated_invoice.remove_conversion(Currency.BBD)
    updated_invoice.add_conversion(Decimal(10), Currency.SYP)
    updated_invoice.add_conversion(Decimal(8), Currency.IRR)

    repository.update(updated_invoice)

    actual = repository.get_by_id(new_id)
    assert actual.id == updated_invoice.id
    assert_invoice_eq(updated_invoice, actual)


@pytest.mark.django_db
def test__unsaved_invoice__update__raises_error() -> None:
    invoice = full_invoice()

    with pytest.raises(repository.UnsavedInvoice):
        repository.update(invoice)


@pytest.mark.django_db
def test__given_paid_invoice_with_publication__invoice_with_publication__returns_invoice() -> None:
    publication_id = random_publication()
    invoice = create_invoice_with_publication(publication_id)
    invoice.id = repository.create(invoice)

    actual = repository.invoice_with_publication(publication_id)

    assert actual is not None
    assert_invoice_eq(invoice, actual)


@pytest.mark.django_db
def test__invoice_with_vat_position__invoice_list_item__has_only_tax_costs() -> None:
    creditor = CreditorId(modelfactory.creditor().pk)
    position_1 = domainfactory.free_position(cost_type=PublicationCostType.Vat)
    invoice = domainfactory.invoice(positions=[position_1], creditor=creditor)
    invoice.id = repository.create(invoice)

    actual, *_ = repository.search()

    assert actual.net == Money(0, position_1.cost.currency)
    assert actual.total == actual.tax == position_1.total()


@pytest.mark.django_db
def test__has_errors_criterion__filters_invoices_with_invalid_contract_years() -> None:
    """Test that has_errors=True filters for invoices with invalid contract years."""
    # Create a contract with a specific period
    contract = domainfactory.contract(
        period=DateRange.create(
            start=_faker.date_between(start_date="-5y", end_date="-3y"),
            end=_faker.date_between(start_date="-2y", end_date="-1y"),
        )
    )
    contract.id = contract_services.create(contract)

    # Create invoice with VALID contract year (within period)
    valid_contract_year = contract.in_year(contract.period.start.year)
    valid_position = domainfactory.contract_position(contract=valid_contract_year)
    valid_invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[valid_position]
    )
    valid_invoice.id = repository.create(valid_invoice)

    # Create invoice with INVALID contract year (before period)
    invalid_year_before = contract.period.start.year - 1
    invalid_contract_year_before = ContractYear(invalid_year_before, contract)
    invalid_position_before = domainfactory.contract_position(contract=invalid_contract_year_before)
    invalid_invoice_before = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[invalid_position_before]
    )
    invalid_invoice_before.id = repository.create(invalid_invoice_before)

    # Create invoice with INVALID contract year (after period)
    invalid_year_after = contract.period.end.year + 1
    invalid_contract_year_after = ContractYear(invalid_year_after, contract)
    invalid_position_after = domainfactory.contract_position(contract=invalid_contract_year_after)
    invalid_invoice_after = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[invalid_position_after]
    )
    invalid_invoice_after.id = repository.create(invalid_invoice_after)

    # Create invoice without contract positions
    no_contract_invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[domainfactory.free_position()]
    )
    no_contract_invoice.id = repository.create(no_contract_invoice)

    # Search with has_errors=True
    results_with_errors = list(repository.search(has_errors=True))
    result_ids_with_errors = {r.id for r in results_with_errors}

    # Should only return invoices with invalid contract years
    assert invalid_invoice_before.id in result_ids_with_errors
    assert invalid_invoice_after.id in result_ids_with_errors
    assert valid_invoice.id not in result_ids_with_errors
    assert no_contract_invoice.id not in result_ids_with_errors

    # Search with has_errors=False (should return all)
    results_all = list(repository.search(has_errors=False))
    result_ids_all = {r.id for r in results_all}

    assert invalid_invoice_before.id in result_ids_all
    assert invalid_invoice_after.id in result_ids_all
    assert valid_invoice.id in result_ids_all
    assert no_contract_invoice.id in result_ids_all


@pytest.mark.django_db
def test__has_errors_criterion__list_item_has_error_flag() -> None:
    """Test that invoices with invalid contract years have the has_invalid_contract_years flag set."""
    # Create a contract with a specific period
    contract = domainfactory.contract(
        period=DateRange.create(
            start=_faker.date_between(start_date="-5y", end_date="-3y"),
            end=_faker.date_between(start_date="-2y", end_date="-1y"),
        )
    )
    contract.id = contract_services.create(contract)

    # Create invoice with INVALID contract year
    invalid_year = contract.period.start.year - 1
    invalid_contract_year = ContractYear(invalid_year, contract)
    invalid_position = domainfactory.contract_position(contract=invalid_contract_year)
    invalid_invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[invalid_position]
    )
    invalid_invoice.id = repository.create(invalid_invoice)

    # Search and check the flag
    results = list(repository.search())
    invoice_item = next(r for r in results if r.id == invalid_invoice.id)

    assert invoice_item.has_invalid_contract_years is True


def create_invoice_with_publication(publication_id: PublicationId) -> Invoice:
    return domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.publication_position(publication=publication_id)],
    )


def full_invoice() -> Invoice:
    creditor_id = CreditorId(modelfactory.creditor().pk)
    publisher_id = PublisherId(modelfactory.publisher().pk)
    publications = [random_publication(publisher_id) for _ in range(3)]
    contracts = [domainfactory.contract_year(random_contract()) for _ in range(3)]

    invoice = domainfactory.invoice(
        creditor=CreditorId(creditor_id),
        positions=(
            *[publication_position(publication) for publication in publications],
            *[contract_position(contract) for contract in contracts],
            *[free_position() for _ in range(3)],
        ),
    )

    invoice.add_conversion(Decimal(5), Currency.BBD)
    invoice.add_conversion(Decimal(2), Currency.SYP)

    return invoice


def publication_position(publication: PublicationId) -> Position:
    position = domainfactory.publication_position(
        publication=publication,
        currency=Currency.FJD,
    )
    _assign_funding(position)

    return position


def contract_position(contract: ContractYear) -> Position:
    position = domainfactory.contract_position(
        contract=contract,
        currency=Currency.FJD,
    )
    _assign_funding(position)
    return position


def free_position() -> Position:
    position = domainfactory.free_position(currency=Currency.FJD)
    _assign_funding(position)
    return position


def _assign_funding(position: Position) -> None:
    position_total = position.net().amount
    partial = position_total / Decimal(5)

    budget_1 = domainfactory.budget()
    budget_2 = domainfactory.budget()
    budget_1.id = funding_source_repository.create(budget_1)
    budget_2.id = funding_source_repository.create(budget_2)

    institution = modelfactory.institution()
    saved_institution_source = domainfactory.split_source(
        InstitutionId(institution.pk), institution.name
    )
    saved_institution_source.id = funding_source_repository.create(saved_institution_source)

    institution_2 = modelfactory.institution()
    unsaved_institution_source = domainfactory.split_source(
        InstitutionId(institution_2.pk), institution_2.name
    )

    position.assign_funding(budget_1, partial)
    position.assign_funding(budget_2, partial)
    position.assign_funding(saved_institution_source, partial)
    position.assign_remaining(unsaved_institution_source)


def random_publication(publisher_id: int | None = None) -> PublicationId:
    journal_id = JournalId(modelfactory.journal(publisher_id).pk)
    funding_organization_id = FundingOrganizationId(modelfactory.funding_organization().pk)
    fundingrequest = domainfactory.fundingrequest(
        journal_id=journal_id, funding_org_id=funding_organization_id
    )
    fundingrequest.id = fundingrequest_repository.create(fundingrequest)
    return cast(PublicationId, fundingrequest.publication.id)


def random_contract() -> Contract:
    contract = domainfactory.contract()
    contract.id = contract_services.create(contract)
    return contract


def assert_invoice_eq(expected: Invoice, actual: Invoice) -> None:
    assert expected.number == actual.number
    assert expected.creditor == actual.creditor
    assert list(expected.positions) == list(actual.positions)
    assert expected.status == actual.status
    assert expected.date == actual.date
    assert expected.comment == actual.comment
    assert expected.external_invoice_id == actual.external_invoice_id
    assert expected.currency() == actual.currency()
    assert expected.total() == actual.total()
    assert expected.tax() == actual.tax()

    assert expected.conversions() == actual.conversions()


@pytest.mark.django_db
def test__bulk_create_invoices__creates_all_invoices() -> None:
    """Test that bulk_create creates all invoice records correctly."""
    invoices = [full_invoice() for _ in range(5)]

    ids = repository.create_many(invoices)

    assert len(ids) == 5
    for invoice_id, original in zip(ids, invoices):
        saved = repository.get_by_id(invoice_id)
        assert_invoice_eq(original, saved)


@pytest.mark.django_db
def test__bulk_create_invoices__creates_all_positions() -> None:
    """Test that bulk_create creates positions for all invoices."""
    # Create invoices with varying numbers of positions
    invoice_1 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.free_position(Currency.AED) for _ in range(3)],
    )
    invoice_2 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.free_position(Currency.JPY) for _ in range(5)],
    )
    invoice_3 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.free_position(Currency.EUR) for _ in range(2)],
    )

    ids = repository.create_many([invoice_1, invoice_2, invoice_3])

    saved_1 = repository.get_by_id(ids[0])
    saved_2 = repository.get_by_id(ids[1])
    saved_3 = repository.get_by_id(ids[2])

    assert_invoice_eq(invoice_1, saved_1)
    assert_invoice_eq(invoice_2, saved_2)
    assert_invoice_eq(invoice_3, saved_3)


@pytest.mark.django_db
def test__bulk_create_invoices__creates_all_currency_conversions() -> None:
    """Test that bulk_create creates currency conversions for all invoices."""
    invoice_1 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.free_position()],
    )
    invoice_1.add_conversion(Decimal("1.5"), Currency.USD)
    invoice_1.add_conversion(Decimal("2.0"), Currency.GBP)

    invoice_2 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[domainfactory.free_position()],
    )
    invoice_2.add_conversion(Decimal("3.0"), Currency.JPY)

    ids = repository.create_many([invoice_1, invoice_2])

    saved_1 = repository.get_by_id(ids[0])
    saved_2 = repository.get_by_id(ids[1])

    assert saved_1.conversions() == {Currency.USD: Decimal("1.5"), Currency.GBP: Decimal("2.0")}
    assert saved_2.conversions() == {Currency.JPY: Decimal("3.0")}


@pytest.mark.django_db
def test__bulk_create_invoices__creates_all_funding_assignments() -> None:
    """Test that bulk_create creates funding assignments for all invoices."""
    position_1 = domainfactory.free_position(currency=Currency.EUR)
    _assign_funding(position_1)

    position_2 = domainfactory.free_position(currency=Currency.EUR)
    _assign_funding(position_2)

    invoice_1 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position_1]
    )
    invoice_2 = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=[position_2]
    )

    ids = repository.create_many([invoice_1, invoice_2])

    saved_1 = repository.get_by_id(ids[0])
    saved_2 = repository.get_by_id(ids[1])

    assert_invoice_eq(invoice_1, saved_1)
    assert_invoice_eq(invoice_2, saved_2)


@pytest.mark.django_db
def test__bulk_create_invoices__with_no_positions__succeeds() -> None:
    """Test that bulk_create handles invoices with no positions gracefully."""
    invoice = domainfactory.invoice(creditor=CreditorId(modelfactory.creditor().pk), positions=[])

    ids = repository.create_many([invoice])

    assert len(ids) == 1
    saved = repository.get_by_id(ids[0])
    assert len(list(saved.positions)) == 0


@pytest.mark.django_db
def test__bulk_create_invoices__with_empty_list__returns_empty_list() -> None:
    """Test that bulk_create with empty list returns empty list."""
    ids = repository.create_many([])
    assert ids == []


@pytest.mark.django_db
def test__bulk_create_invoices__mixed_position_types__creates_correctly() -> None:
    """Test bulk_create with mixed position types (publication, contract, free)."""
    creditor = CreditorId(modelfactory.creditor().pk)
    publication_id = random_publication()
    contract = random_contract()
    contract_year = domainfactory.contract_year(contract)

    invoice_1 = domainfactory.invoice(
        creditor=creditor,
        positions=[
            domainfactory.publication_position(publication=publication_id, currency=Currency.AED),
            domainfactory.contract_position(contract=contract_year, currency=Currency.AED),
            domainfactory.free_position(currency=Currency.AED),
        ],
    )

    invoice_2 = domainfactory.invoice(
        creditor=creditor,
        positions=[
            domainfactory.free_position(currency=Currency.AED),
            domainfactory.free_position(currency=Currency.AED),
        ],
    )

    ids = repository.create_many([invoice_1, invoice_2])

    saved_1 = repository.get_by_id(ids[0])
    saved_2 = repository.get_by_id(ids[1])

    assert_invoice_eq(invoice_1, saved_1)
    assert_invoice_eq(invoice_2, saved_2)
