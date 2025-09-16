import dataclasses
from typing import cast

import pytest

from coda.apps.invoices import repository, services
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.domain.invoice import AnyPosition, CreditorId, Invoice, InvoiceId
from coda.domain.publication.payment import (
    IndividuallyBilledPublicationPayments,
    Payment,
    IndividualPublicationPaymentStatus,
)
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__unpaid_invoice_with_publication__save__publication_has_invoice_received() -> None:
    publication = create_publication()
    invoice = unpaid_invoice_for_publications(publication)
    invoice.id = services.save(invoice)

    assert_invoice_received(invoice, publication)


def assert_invoice_received(invoice: Invoice, publication: PublicationId) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, IndividuallyBilledPublicationPayments)
    assert payment_status.status() == IndividualPublicationPaymentStatus.Unpaid
    assert payment_status.payments() == [
        Payment(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=True)
    ]


@pytest.mark.django_db
def test__paid_invoice__save__publications_are_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.pay()

    invoice.id = services.save(invoice)

    assert_publication_paid(invoice, publication_1)
    assert_publication_paid(invoice, publication_2)


def assert_publication_paid(invoice: Invoice, publication: PublicationId) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, IndividuallyBilledPublicationPayments)
    assert payment_status.status() == IndividualPublicationPaymentStatus.Paid
    assert payment_status.payments() == [
        Payment(
            invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=False
        )
    ]


@pytest.mark.django_db
def test__invoice__pay_invoice__invoice_is_paid() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = services.save(invoice)

    services.pay_invoice(invoice.id)

    actual = repository.get_by_id(invoice.id)
    assert actual.is_paid()


@pytest.mark.django_db
def test__invoice__pay_invoice_with_publications__all_publication_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.id = repository.create(invoice)

    services.pay_invoice(invoice.id)

    assert_publication_paid(invoice, publication_1)
    assert_publication_paid(invoice, publication_2)


@pytest.mark.django_db
def test__paid_invoice__reset_payment__invoice_is_not_paid() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = repository.create(invoice)

    services.reset_payment(invoice.id)

    actual = repository.get_by_id(invoice.id)
    assert not actual.is_paid()


@pytest.mark.django_db
def test__paid_invoice_with_publications__reset_payment__all_publication_have_invoice_received() -> (
    None
):
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.id = repository.create(invoice)

    services.pay_invoice(invoice.id)
    services.reset_payment(invoice.id)

    assert_invoice_received(invoice, publication_1)
    assert_invoice_received(invoice, publication_2)


@pytest.mark.django_db
def test__invoice__delete_invoice__invoice_is_deleted() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = repository.create(invoice)

    services.delete_invoice(invoice.id)

    with pytest.raises(Exception):
        repository.get_by_id(invoice.id)


@pytest.mark.django_db
def test__invoice_with_publications__delete_invoice__publications_are_unpaid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.id = repository.create(invoice)
    services.pay_invoice(invoice.id)

    services.delete_invoice(invoice.id)

    assert_publication_unpaid(publication_1)
    assert_publication_unpaid(publication_2)


def assert_publication_unpaid(publication: PublicationId) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, IndividuallyBilledPublicationPayments)
    assert payment_status.status() == IndividualPublicationPaymentStatus.Unpaid


@pytest.mark.django_db
def test__paid_invoice_with_publication__delete_publication_position__publication_is_unpaid() -> (
    None
):
    publication = create_publication()
    invoice = unpaid_invoice_for_publications(publication)
    invoice.id = repository.create(invoice)
    services.pay_invoice(invoice.id)

    invoice.positions = []
    services.save(invoice)

    assert_publication_unpaid(publication)


@pytest.mark.django_db
def test__paid_invoice_with_two_equal_publication_positions__delete_one__publication_is_still_paid() -> (
    None
):
    publication = create_publication()
    position = domainfactory.publication_position(publication)
    equal_position = dataclasses.replace(position)

    invoice = paid_invoice(position, equal_position)
    invoice.id = services.save(invoice)

    invoice.positions = [equal_position]
    services.save(invoice)

    assert_publication_paid(invoice, publication)


@pytest.mark.django_db
def test__two_paid_invoices_have_the_same_publication__removing_publication_from_one_invoice__publication_still_paid() -> (
    None
):
    publication = create_publication()

    invoice = paid_invoice_for_publication(publication)
    invoice.id = services.save(invoice)

    invoice2 = paid_invoice_for_publication(publication)
    invoice2.id = services.save(invoice2)

    invoice2.positions = []
    services.save(invoice2)

    assert_publication_paid(invoice, publication)


@pytest.mark.django_db
def test__one_invoice_paid_one_invoice_unpaid__removing_publication_from_paid_invoice__publication_unpaid() -> (
    None
):
    publication = create_publication()
    invoice = paid_invoice_for_publication(publication)
    invoice.id = services.save(invoice)

    invoice2 = unpaid_invoice_for_publications(publication)
    invoice2.id = services.save(invoice2)

    invoice.positions = []
    services.save(invoice)

    assert_publication_unpaid(publication)


@pytest.mark.django_db
def test__publication_on_paid_unpaid_and_paid_invoice__removing_publication_from_first_paid_invoice__publication_is_still_paid() -> (
    None
):
    publication = create_publication()

    first_paid = paid_invoice_for_publication(publication)
    first_paid.id = services.save(first_paid)

    unpaid = unpaid_invoice_for_publications(publication)
    unpaid.id = services.save(unpaid)

    second_paid = paid_invoice_for_publication(publication)
    second_paid.id = services.save(second_paid)

    first_paid.positions = []
    services.save(first_paid)

    assert_publication_paid(second_paid, publication)


def paid_invoice_for_publication(publication: PublicationId) -> Invoice:
    position = domainfactory.publication_position(publication)
    return paid_invoice(position)


def paid_invoice(*positions: AnyPosition) -> Invoice:
    creditor = CreditorId(modelfactory.creditor().id)
    invoice = domainfactory.invoice(positions=tuple(positions), creditor=creditor)
    invoice.pay()
    return invoice


def unpaid_invoice_for_publications(*publication_ids: PublicationId) -> Invoice:
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
    publication.id = publication_repository.create(publication)
    return publication.id
