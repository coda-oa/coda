from typing import cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.apps.publications.services import publications
from coda.domain.contract import ContractYear, PublicationBilling
from coda.domain.invoice import CreditorId, Invoice, InvoiceId
from coda.domain.publication.payment import (
    InvoiceReceived,
    InvoicePaymentReset,
    Payment,
    PublicationCoveredByContract,
    PublicationPaid,
    PublicationPayments,
)
from coda.domain.publication.publication import JournalId, PublicationId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__publication_with_paid_invoice__mark_paid__publication_is_paid() -> None:
    publication = create_publication()
    invoice = pay_publication(publication)

    paid = PublicationPaid(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number)
    publications.update_payment(publication, paid)

    payment_status = publications.get_payment_status(publication)
    assert isinstance(payment_status, PublicationPayments)
    assert payment_status.all_paid()
    assert payment_status.payments() == [
        Payment(
            invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=False
        )
    ]


@pytest.mark.django_db
def test__publication_without_invoice__has_no_payments() -> None:
    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal)
    publication.id = publication_repository.create(publication)

    payment_status = get_individual_paymentstatus(publication.id)
    assert payment_status.payments() == []


def get_individual_paymentstatus(
    publication_id: PublicationId,
) -> PublicationPayments:
    payment_status = publications.get_payment_status(publication_id)
    assert isinstance(payment_status, PublicationPayments)
    return payment_status


@pytest.mark.django_db
def test__publication_with_paid_invoice__not_marked_paid__has_no_payments() -> None:
    publication_id = create_publication()
    create_invoice_for_publication(publication_id)

    assert get_individual_paymentstatus(publication_id).payments() == []


@pytest.mark.django_db
def test__publication_with_unpaid_invoice__invoice_received__publication_has_invoice_received() -> (
    None
):
    publication_id = create_publication()
    invoice = create_invoice_for_publication(publication_id)

    invoice_received = InvoiceReceived(
        invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number
    )

    publications.update_payment(publication_id, invoice_received)

    payment_status = get_individual_paymentstatus(publication_id)
    assert payment_status.has_pending_payments()
    assert payment_status.payments() == [
        Payment(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=True)
    ]


@pytest.mark.django_db
def test__publication_with_invoice_received__invoice_paid__publication_is_paid() -> None:
    publication_id = create_publication()
    invoice = create_invoice_for_publication(publication_id)
    invoice_received = InvoiceReceived(
        invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number
    )
    publications.update_payment(publication_id, invoice_received)

    invoice.pay()
    invoice_repository.update(invoice)
    publications.update_payment(
        publication_id, PublicationPaid(cast(InvoiceId, invoice.id), invoice.number)
    )

    payment_status = get_individual_paymentstatus(publication_id)
    assert payment_status.all_paid()
    assert payment_status.payments() == [
        Payment(cast(InvoiceId, invoice.id), invoice.number, pending=False)
    ]


@pytest.mark.django_db
def test__publication_with_paid_invoice__new_invoice_received__publication_is_partially_paid() -> (
    None
):
    publication_id = create_publication()
    invoice = pay_publication(publication_id)
    publications.update_payment(
        publication_id,
        PublicationPaid(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number),
    )

    next_invoice = create_invoice_for_publication(publication_id)
    publications.update_payment(
        publication_id,
        InvoiceReceived(
            invoice_id=cast(InvoiceId, next_invoice.id), invoice_number=next_invoice.number
        ),
    )

    payment_status = get_individual_paymentstatus(publication_id)
    assert payment_status.has_pending_payments()
    assert payment_status.partially_paid()
    assert payment_status.payments() == [
        Payment(
            invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=False
        ),
        Payment(
            invoice_id=cast(InvoiceId, next_invoice.id),
            invoice_number=next_invoice.number,
            pending=True,
        ),
    ]


@pytest.mark.django_db
def test__publicatoin_with_two_paid_invoices__unpay_one_publication__publication_is_partially_paid() -> (
    None
):
    publication_id = create_publication()
    first_invoice = pay_publication(publication_id)
    second_invoice = pay_publication(publication_id)

    publications.update_payment(
        publication_id, PublicationPaid(cast(InvoiceId, first_invoice.id), first_invoice.number)
    )
    publications.update_payment(
        publication_id, PublicationPaid(cast(InvoiceId, second_invoice.id), second_invoice.number)
    )

    publications.update_payment(
        publication_id, InvoicePaymentReset(cast(InvoiceId, first_invoice.id))
    )

    payment_status = get_individual_paymentstatus(publication_id)
    assert payment_status.partially_paid()


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__unpaid_publication_without_invoice__publication_has_no_payments() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.create(contract)

    publication = create_publication(contract.in_first_year())

    payment_status = get_individual_paymentstatus(publication)

    assert not payment_status.has_pending_payments()


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__paid_publication__payments_all_paid() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.create(contract)

    publication = create_publication(contract.in_first_year())
    invoice = pay_publication(publication)

    paid = PublicationPaid(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number)
    publications.update_payment(publication, paid)

    payment_status = get_individual_paymentstatus(publication)

    assert payment_status.all_paid()


@pytest.mark.django_db
def test__contract_with_individual_publication_billing__unpaid_publication_with_received_invoice__has_pending_payments() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Individually
    contract.id = contract_repository.create(contract)

    publication = create_publication(contract.in_first_year())
    invoice = create_invoice_for_publication(publication)
    invoice_received = InvoiceReceived(
        invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number
    )

    publications.update_payment(publication, invoice_received)
    payment_status = get_individual_paymentstatus(publication)

    assert payment_status.has_pending_payments()
    assert payment_status.payments() == [
        Payment(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number, pending=True)
    ]


@pytest.mark.django_db
def test__contract_with_consolidated_publication_billing__payment_status_is_covered_by_contract() -> (
    None
):
    contract = domainfactory.contract()
    contract.publication_billing = PublicationBilling.Consolidated
    contract.id = contract_repository.create(contract)

    contract_year = contract.in_first_year()
    publication = create_publication(contract_year)

    payment_status = publications.get_payment_status(publication)

    assert payment_status == PublicationCoveredByContract(
        contract_id=contract.id,
        contract_name=contract_year.name,
        contract_year=contract_year.year,
    )


@pytest.mark.django_db
def test__paid_publication__invoice_deleted__publication_has_no_payments() -> None:
    publication = create_publication()
    invoice = pay_publication(publication)
    publications.update_payment(
        publication,
        PublicationPaid(invoice_id=cast(InvoiceId, invoice.id), invoice_number=invoice.number),
    )

    publications.invoice_deleted(publication, cast(InvoiceId, invoice.id))
    payments = get_individual_paymentstatus(publication)
    assert payments.payments() == []


def pay_publication(publication: PublicationId) -> Invoice:
    invoice = create_invoice_for_publication(publication)
    invoice.pay()
    invoice_repository.update(invoice)
    return invoice


def create_invoice_for_publication(publication: PublicationId) -> Invoice:
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().id),
        positions=[domainfactory.publication_position(publication)],
    )
    invoice.reset_payment()

    invoice.id = invoice_repository.create(invoice)
    return invoice


def create_publication(contract: ContractYear | None = None) -> PublicationId:
    journal = JournalId(modelfactory.journal().id)
    contracts = (contract,) if contract else ()
    publication = domainfactory.publication(journal, contracts=contracts)
    publication.id = publication_repository.create(publication)
    return publication.id
