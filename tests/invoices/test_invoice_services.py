import pytest

from coda.apps.authors.services import author_create
from coda.apps.invoices import services
from coda.apps.publications.services import publication_create
from coda.invoice import Invoice, CreditorId
from coda.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__create_invoice__saves_invoice_to_database() -> None:
    publisher_id = modelfactory.publisher().id
    publications = [random_publication(publisher_id) for _ in range(3)]
    invoice = domainfactory.invoice(
        creditor=CreditorId(publisher_id),
        positions=[
            *[
                domainfactory.publication_position(publication=publication)
                for publication in publications
            ],
            *[domainfactory.free_position() for _ in range(3)],
        ],
    )

    new_id = services.invoice_create(invoice)

    actual = services.get_by_id(new_id)
    assert_invoice_eq(invoice, actual)


def random_publication(publisher_id: int) -> PublicationId:
    journal_id = modelfactory.journal(publisher_id).id
    author_id = author_create(domainfactory.author())
    return publication_create(domainfactory.publication(journal=JournalId(journal_id)), author_id)


def assert_invoice_eq(expected: Invoice, actual: Invoice) -> None:
    assert expected.number == actual.number
    assert expected.creditor == actual.creditor
    assert expected.positions == actual.positions
