from collections.abc import Iterable, Sequence

from django.db import transaction
from django.db.models import QuerySet

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices import mapper as invoice_mapper
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.domain.finance.invoice import CreditorId, Invoice, InvoiceId, PaymentStatus
from coda.domain.publication import PublicationId


def first() -> Invoice | None:
    model = InvoiceModel.objects.first()
    if not model:
        return None

    return invoice_mapper.as_domain_object(model)


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    return invoice_mapper.as_domain_object(InvoiceModel.objects.get(id=invoice_id))


def get_by_creditor(creditor_id: CreditorId) -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.filter(creditor_id=creditor_id)),
        invoice_mapper.as_domain_object,
    )


def all() -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.all()), invoice_mapper.as_domain_object
    )


def invoice_with_publication(publication_id: PublicationId) -> Invoice | None:
    invoice = InvoiceModel.objects.filter(positions__publication_id=publication_id).first()

    if not invoice:
        return None

    return invoice_mapper.as_domain_object(invoice)


def get_other_paid_invoice_with_publication(
    original_invoice: Invoice, publication_id: PublicationId
) -> Invoice | None:
    if not original_invoice.id:
        raise UnsavedInvoice(original_invoice)

    invoice = (
        InvoiceModel.objects.filter(
            positions__publication_id=publication_id,
            status=PaymentStatus.Paid.value,
        )
        .exclude(id=original_invoice.id)
        .first()
    )

    if not invoice:
        return None

    return invoice_mapper.as_domain_object(invoice)


def create(invoice: Invoice) -> InvoiceId:
    if invoice.id:
        raise InvoiceAlreadyExists(invoice.id)

    invoice_model = invoice_mapper.as_django_model(invoice)
    invoice_model.save()
    invoice_mapper.synchronize_relationships(invoice, invoice_model)

    return InvoiceId(invoice_model.pk)


@transaction.atomic
def create_many(invoices: Iterable[Invoice]) -> list[InvoiceId]:
    # Convert to list to enable reuse in both bulk_create and synchronize_relationships_bulk
    invoices_list = list(invoices)

    # Bulk create invoice records
    models = InvoiceModel.objects.bulk_create(
        invoice_mapper.as_django_model(invoice) for invoice in invoices_list
    )

    # Use optimized bulk relationship synchronization (3 queries instead of 5N)
    invoice_mapper.synchronize_relationships_bulk(invoices_list, models)

    return [InvoiceId(m.pk) for m in models]


def update(invoice: Invoice) -> None:
    if not invoice.id:
        raise UnsavedInvoice(invoice)

    invoice_model = invoice_mapper.as_django_model(invoice)
    invoice_mapper.synchronize_relationships(invoice, invoice_model)
    invoice_model.save()


def delete(invoice_id: InvoiceId) -> None:
    InvoiceModel.objects.filter(id=invoice_id).delete()


class InvoiceAlreadyExists(ValueError):
    def __init__(self, invoice_id: InvoiceId) -> None:
        super().__init__(f"Invoice with ID {invoice_id} already exists.")


class UnsavedInvoice(ValueError):
    def __init__(self, invoice: Invoice) -> None:
        super().__init__(f"Invoice {invoice.number} is not saved yet.")


def _ordered_date_desc(invoices: QuerySet[InvoiceModel]) -> QuerySet[InvoiceModel]:
    return invoices.order_by("-date")
