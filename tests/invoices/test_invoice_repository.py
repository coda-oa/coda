from decimal import Decimal
from typing import cast

import faker
import pytest

from coda.apps.contracts import repository as contract_services
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.invoices import funding_source_repository, repository
from coda.domain.author import InstitutionId
from coda.domain.contract import Contract, ContractYear, PublisherId
from coda.domain.finance.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.domain.finance.invoice_positions import Position
from coda.domain.fundingrequest import FundingOrganizationId
from coda.domain.money._currency import Currency
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
        positions=[
            *[publication_position(publication) for publication in publications],
            *[contract_position(contract) for contract in contracts],
            *[free_position() for _ in range(3)],
        ],
    )

    invoice.add_conversion(Decimal(5), Currency.BBD)
    invoice.add_conversion(Decimal(2), Currency.SYP)

    return invoice


def publication_position(publication: PublicationId) -> Position:
    funding_source_id = FundingSourceId(modelfactory.budget().pk)
    position = domainfactory.publication_position(
        publication=publication,
        funding_source=funding_source_id,
        currency=Currency.FJD,
    )
    _assign_funding(position)

    return position


def contract_position(contract: ContractYear) -> Position:
    funding_source_id = FundingSourceId(modelfactory.budget().pk)
    position = domainfactory.contract_position(
        contract=contract,
        funding_source=funding_source_id,
        currency=Currency.FJD,
    )
    _assign_funding(position)
    return position


def free_position() -> Position:
    position = domainfactory.free_position(currency=Currency.FJD)
    _assign_funding(position)
    return position


def _assign_funding(position: Position) -> None:
    institution = modelfactory.institution()
    position_total = position.net().amount
    partial = position_total / Decimal(3)
    budget_1 = domainfactory.budget()
    budget_2 = domainfactory.budget()
    institution_source = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    budget_1.id = funding_source_repository.create(budget_1)
    budget_2.id = funding_source_repository.create(budget_2)
    institution_source.id = funding_source_repository.create(institution_source)

    position.assign_funding(budget_1, partial)
    position.assign_funding(budget_2, partial)

    remainder = position.unassigned_costs().amount
    position.assign_funding(institution_source, remainder)


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
