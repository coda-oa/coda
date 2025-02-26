import faker
import pytest

from coda.apps.contracts import repository as contract_services
from coda.apps.invoices import repository
from coda.apps.publications.repositories import publication_repository
from coda.contract import Contract
from coda.invoice import CreditorId, FundingSourceId, Invoice, PaymentStatus
from coda.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory

_faker = faker.Faker()


@pytest.mark.django_db
def test__save_new_invoice__saves_invoice_to_database() -> None:
    invoice = full_invoice()

    new_id = repository.save(invoice)

    actual = repository.get_by_id(new_id)
    assert_invoice_eq(invoice, actual)


@pytest.mark.django_db
def test__given_updated_invoice__save__updates_invoice_in_database() -> None:
    invoice = full_invoice()
    invoice.status = PaymentStatus.Unpaid

    new_id = repository.save(invoice)

    updated_invoice = repository.get_by_id(new_id)
    updated_invoice.number = "updated"
    updated_invoice.creditor = CreditorId(modelfactory.creditor().id)
    updated_invoice.status = PaymentStatus.Paid
    updated_invoice.date = _faker.date_object()
    updated_invoice.positions = [domainfactory.free_position()]
    updated_invoice.comment = "updated"
    updated_invoice.external_invoice_id = "updated"

    repository.save(updated_invoice)

    actual = repository.get_by_id(new_id)
    assert actual.id == updated_invoice.id
    assert_invoice_eq(updated_invoice, actual)


@pytest.mark.django_db
def test__given_paid_invoice_with_publication__invoice_with_publication__returns_invoice() -> None:
    publication_id = random_publication()
    invoice = create_invoice_with_publication(publication_id)
    invoice.id = repository.save(invoice)

    actual = repository.invoice_with_publication(publication_id)

    assert actual is not None
    assert_invoice_eq(invoice, actual)


def create_invoice_with_publication(publication_id: PublicationId) -> Invoice:
    return domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().id),
        positions=[domainfactory.publication_position(publication=publication_id)],
    )


def full_invoice() -> Invoice:
    creditor_id = modelfactory.creditor().id
    funding_source_id = FundingSourceId(modelfactory.funding_source().id)
    publisher_id = modelfactory.publisher().id
    publications = [random_publication(publisher_id) for _ in range(3)]
    contracts = [domainfactory.contract_year(random_contract()) for _ in range(3)]

    invoice = domainfactory.invoice(
        creditor=CreditorId(creditor_id),
        positions=[
            *[
                domainfactory.publication_position(
                    publication=publication, funding_source=funding_source_id
                )
                for publication in publications
            ],
            *[
                domainfactory.contract_position(contract=contract, funding_source=funding_source_id)
                for contract in contracts
            ],
            *[domainfactory.free_position() for _ in range(3)],
        ],
    )

    return invoice


def random_publication(publisher_id: int | None = None) -> PublicationId:
    journal_id = modelfactory.journal(publisher_id).id
    return publication_repository.save(domainfactory.publication(journal=JournalId(journal_id)))


def random_contract() -> Contract:
    contract = domainfactory.contract()
    contract.id = contract_services.save(contract)
    return contract


def assert_invoice_eq(expected: Invoice, actual: Invoice) -> None:
    assert expected.number == actual.number
    assert expected.creditor == actual.creditor
    assert expected.positions == actual.positions
    assert expected.status == actual.status
    assert expected.date == actual.date
    assert expected.comment == actual.comment
    assert expected.external_invoice_id == actual.external_invoice_id
