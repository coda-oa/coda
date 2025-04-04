import pytest

from coda.apps.invoices import repository, services
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.domain.invoice import CreditorId, Invoice
from coda.domain.publication.payment import InvoiceReceived, PublicationPaid, PublicationUnpaid
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__unpaid_invoice_with_publication__save__publication_has_invoice_received() -> None:
    publication = create_publication()
    invoice = unpaid_invoice(publication)
    invoice.id = services.save(invoice)

    invoice_received = InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
    assert publications.get_payment_status(publication) == invoice_received


@pytest.mark.django_db
def test__paid_invoice__save__publications_are_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice(publication_1, publication_2)
    invoice.pay()

    invoice.id = services.save(invoice)

    paid = PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)
    assert publications.get_payment_status(publication_1) == paid
    assert publications.get_payment_status(publication_2) == paid


@pytest.mark.django_db
def test__invoice__pay_invoice__invoice_is_paid() -> None:
    invoice = unpaid_invoice()
    invoice.id = services.save(invoice)

    services.pay_invoice(invoice.id)

    actual = repository.get_by_id(invoice.id)
    assert actual.is_paid()


@pytest.mark.django_db
def test__invoice__pay_invoice_with_publications__all_publication_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice(publication_1, publication_2)
    invoice.id = repository.save(invoice)

    services.pay_invoice(invoice.id)

    paid = PublicationPaid(invoice_id=invoice.id, invoice_number=invoice.number)
    assert publications.get_payment_status(publication_1) == paid
    assert publications.get_payment_status(publication_2) == paid


@pytest.mark.django_db
def test__paid_invoice__reset_payment__invoice_is_not_paid() -> None:
    invoice = unpaid_invoice()
    invoice.id = repository.save(invoice)

    services.reset_payment(invoice.id)

    actual = repository.get_by_id(invoice.id)
    assert not actual.is_paid()


@pytest.mark.django_db
def test__paid_invoice_with_publications__reset_payment__all_publication_have_invoice_received() -> (
    None
):
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice(publication_1, publication_2)
    invoice.id = repository.save(invoice)

    services.pay_invoice(invoice.id)
    services.reset_payment(invoice.id)

    invoice_received = InvoiceReceived(invoice_id=invoice.id, invoice_number=invoice.number)
    assert publications.get_payment_status(publication_1) == invoice_received
    assert publications.get_payment_status(publication_2) == invoice_received


@pytest.mark.django_db
def test__invoice__delete_invoice__invoice_is_deleted() -> None:
    invoice = unpaid_invoice()
    invoice.id = repository.save(invoice)

    services.delete_invoice(invoice.id)

    with pytest.raises(Exception):
        repository.get_by_id(invoice.id)


@pytest.mark.django_db
def test__invoice_with_publications__delete_invoice__publications_are_unpaid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice(publication_1, publication_2)
    invoice.id = repository.save(invoice)
    services.pay_invoice(invoice.id)

    services.delete_invoice(invoice.id)

    assert publications.get_payment_status(publication_1) == PublicationUnpaid()
    assert publications.get_payment_status(publication_2) == PublicationUnpaid()


def unpaid_invoice(*publication_ids: PublicationId) -> Invoice:
    creditor = CreditorId(modelfactory.creditor().id)
    positions = tuple(
        domainfactory.publication_position(publication_id) for publication_id in publication_ids
    )

    invoice = domainfactory.invoice(creditor=creditor, positions=positions)
    invoice.reset_payment()
    return invoice


def create_publication() -> PublicationId:
    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal)
    publication.id = publication_repository.save(publication)
    return publication.id
