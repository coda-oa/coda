import pytest

from coda.apps.invoices import repository
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.contexts.finance.services import invoice_service
from coda.domain.author import InstitutionId
from coda.domain.finance import invoice_positions
from coda.domain.finance.funding_sources import SplitSource
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import Position
from coda.domain.publication.payment import Payment, PublicationPayments
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory
from tests.invoices.test_invoice_repository import assert_invoice_eq


@pytest.mark.django_db
def test__invoice_with_position_with_institution_funding__saves_institution_funding_implicitly() -> (
    None
):
    """
    This behavior used to be ensured by the service itself, but has moved to the repository layer.
    We keep this test around anyway for documentation and to ensure this requirement is always fulfilled
    """
    institution = modelfactory.institution()
    invoice = domainfactory.invoice(creditor=CreditorId(modelfactory.creditor().pk))
    position = domainfactory.free_position()

    split_source = SplitSource.new(InstitutionId(institution.pk), institution.name)
    position.assign_remaining(split_source)
    invoice.positions = [position]

    invoice.id = invoice_service.save(invoice)

    first = repository.first()
    assert first is not None
    assert_invoice_eq(invoice, first)


@pytest.mark.django_db
def test__unpaid_invoice_with_publication__save__publication_has_invoice_received() -> None:
    publication = create_publication()
    invoice = unpaid_invoice_for_publications(publication)
    invoice.id = invoice_service.save(invoice)

    assert_invoice_received(invoice, publication)


def assert_invoice_received(invoice: Invoice, publication: PublicationId) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, PublicationPayments)
    assert payment_status.has_pending_payments()
    assert payment_status.payments() == [
        Payment(invoice_id=invoice.id, invoice_number=invoice.number, pending=True)
    ]


@pytest.mark.django_db
def test__paid_invoice__save__publications_are_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.pay()

    invoice.id = invoice_service.save(invoice)

    assert_publication_paid(publication_1, invoice)
    assert_publication_paid(publication_2, invoice)


def assert_publication_paid(publication: PublicationId, *invoices: Invoice) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, PublicationPayments)
    assert payment_status.all_paid()
    assert payment_status.payments() == [
        Payment(
            invoice_id=invoice.id,
            invoice_number=invoice.number,
            pending=False,
        )
        for invoice in invoices
    ]


@pytest.mark.django_db
def test__invoice__pay_invoice__invoice_is_paid() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = invoice_service.save(invoice)

    invoice_service.pay_invoice(invoice.id)

    actual = repository.get_by_id(invoice.id)
    assert actual.is_paid()


@pytest.mark.django_db
def test__invoice__pay_invoice_with_publications__all_publication_paid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.id = repository.create(invoice)

    invoice_service.pay_invoice(invoice.id)

    assert_publication_paid(publication_1, invoice)
    assert_publication_paid(publication_2, invoice)


@pytest.mark.django_db
def test__paid_invoice__reset_payment__invoice_is_not_paid() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = repository.create(invoice)

    invoice_service.reset_payment(invoice.id)

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

    invoice_service.pay_invoice(invoice.id)
    invoice_service.reset_payment(invoice.id)

    assert_invoice_received(invoice, publication_1)
    assert_invoice_received(invoice, publication_2)


@pytest.mark.django_db
def test__invoice__delete_invoice__invoice_is_deleted() -> None:
    invoice = unpaid_invoice_for_publications()
    invoice.id = repository.create(invoice)

    invoice_service.delete_invoice(invoice.id)

    with pytest.raises(Exception):
        repository.get_by_id(invoice.id)


@pytest.mark.django_db
def test__invoice_with_publications__delete_invoice__publications_are_unpaid() -> None:
    publication_1 = create_publication()
    publication_2 = create_publication()
    invoice = unpaid_invoice_for_publications(publication_1, publication_2)
    invoice.id = repository.create(invoice)
    invoice_service.pay_invoice(invoice.id)

    invoice_service.delete_invoice(invoice.id)

    assert_publication_unpaid(publication_1)
    assert_publication_unpaid(publication_2)


def assert_publication_unpaid(publication: PublicationId) -> None:
    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, PublicationPayments)
    assert payment_status.payments() == []


@pytest.mark.django_db
def test__paid_invoice_with_publication__delete_publication_position__publication_is_unpaid() -> (
    None
):
    publication = create_publication()
    invoice = unpaid_invoice_for_publications(publication)
    invoice.id = repository.create(invoice)
    invoice_service.pay_invoice(invoice.id)

    invoice.positions = []
    invoice_service.save(invoice)

    assert_publication_unpaid(publication)


@pytest.mark.django_db
def test__paid_invoice_with_two_equal_publication_positions__delete_one__publication_is_still_paid() -> (
    None
):
    publication = create_publication()
    position = domainfactory.publication_position(publication)
    equal_position = copy_position(position)

    invoice = paid_invoice(position, equal_position)
    invoice.id = invoice_service.save(invoice)

    invoice.positions = [equal_position]
    invoice_service.save(invoice)

    assert_publication_paid(publication, invoice)


def copy_position(position: Position) -> Position:
    return invoice_positions.create(
        item=position.item,
        cost=position.cost,
        tax_rate=position.tax_rate,
        external_position_id=position.external_position_id,
    )


@pytest.mark.django_db
def test__two_paid_invoices_have_the_same_publication__removing_publication_from_one_invoice__publication_still_paid() -> (
    None
):
    publication = create_publication()

    invoice = paid_invoice_for_publication(publication)
    invoice.id = invoice_service.save(invoice)

    invoice2 = paid_invoice_for_publication(publication)
    invoice2.id = invoice_service.save(invoice2)

    invoice2.positions = []
    invoice_service.save(invoice2)

    assert_publication_paid(publication, invoice)


@pytest.mark.django_db
def test__one_invoice_paid_one_invoice_unpaid__removing_publication_from_paid_invoice__publication_unpaid() -> (
    None
):
    publication = create_publication()
    invoice = paid_invoice_for_publication(publication)
    invoice.id = invoice_service.save(invoice)

    invoice2 = unpaid_invoice_for_publications(publication)
    invoice2.id = invoice_service.save(invoice2)

    invoice.positions = []
    invoice_service.save(invoice)

    assert_invoice_received(invoice2, publication)


@pytest.mark.django_db
def test__publication_on_paid_unpaid_and_paid_invoice__removing_publication_from_first_paid_invoice__publication_is_partially_paid() -> (
    None
):
    publication = create_publication()

    first_paid = paid_invoice_for_publication(publication)
    first_paid.id = invoice_service.save(first_paid)

    unpaid = unpaid_invoice_for_publications(publication)
    unpaid.id = invoice_service.save(unpaid)

    second_paid = paid_invoice_for_publication(publication)
    second_paid.id = invoice_service.save(second_paid)

    first_paid.positions = []
    invoice_service.save(first_paid)

    assert_publication_partially_paid(publication, unpaid, second_paid)


def assert_publication_partially_paid(publication: PublicationId, *invoices: Invoice) -> None:
    payments = publications.get_payment_status(publication)
    assert isinstance(payments, PublicationPayments)
    assert payments.has_pending_payments()
    assert payments.partially_paid()

    def _sort_by_id(payments: list[Payment]) -> list[Payment]:
        return sorted(payments, key=lambda p: p.invoice_id.pk)

    assert _sort_by_id(payments.payments()) == _sort_by_id(
        [
            Payment(
                invoice_id=invoice.id,
                invoice_number=invoice.number,
                pending=not invoice.is_paid(),
            )
            for invoice in invoices
        ]
    )


def paid_invoice_for_publication(publication: PublicationId) -> Invoice:
    position = domainfactory.publication_position(publication)
    return paid_invoice(position)


def paid_invoice(*positions: Position) -> Invoice:
    creditor = CreditorId(modelfactory.creditor().pk)
    invoice = domainfactory.invoice(positions=tuple(positions), creditor=creditor)
    invoice.pay()
    return invoice


def unpaid_invoice_for_publications(*publication_ids: PublicationId) -> Invoice:
    creditor = CreditorId(modelfactory.creditor().pk)
    positions = tuple(
        domainfactory.publication_position(publication_id) for publication_id in publication_ids
    )

    invoice = domainfactory.invoice(creditor=creditor, positions=positions)
    invoice.reset_payment()
    return invoice


def create_publication() -> PublicationId:
    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal)
    publication.id = publication_repository.create(publication)
    return publication.id
