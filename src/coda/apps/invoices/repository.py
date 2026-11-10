from collections.abc import Iterable, Sequence

from django.db import transaction
from django.db.models import Q, QuerySet

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.invoices import mapper as invoice_mapper
from coda.apps.invoices.mappers._domain import InvoiceDomainMapper
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.models import Position as PositionModel
from coda.domain.finance.invoice import CreditorId, Invoice, InvoiceId
from coda.domain.publication import PublicationId


def first() -> Invoice | None:
    model = InvoiceDomainMapper.prefetch(InvoiceModel.objects.all()).first()
    if not model:
        return None

    return InvoiceDomainMapper.map(model)


def publication_position_ids(invoice_id: InvoiceId) -> list[PublicationId]:
    """Publication ids of the invoice's positions that map to PublicationItem.

    Mirrors the item precedence in the position mapper: a position with both
    contract and contract_year maps to ContractItem, and its publication does
    not count.
    """
    return [
        PublicationId(pk)
        for pk in PositionModel.objects.filter(
            Q(contract__isnull=True) | Q(contract_year__isnull=True),
            invoice_id=invoice_id,
            publication__isnull=False,
        ).values_list("publication_id", flat=True)
    ]


def get_by_id(invoice_id: InvoiceId) -> Invoice:
    qs = InvoiceDomainMapper.prefetch(InvoiceModel.objects.all())
    return InvoiceDomainMapper.map(qs.get(id=invoice_id))


def get_by_creditor(creditor_id: CreditorId) -> Sequence[Invoice]:
    return DomainQuerySet(
        _ordered_date_desc(InvoiceModel.objects.filter(creditor_id=creditor_id)),
        InvoiceDomainMapper.map,
    )


def all() -> Sequence[Invoice]:
    return DomainQuerySet(_ordered_date_desc(InvoiceModel.objects.all()), InvoiceDomainMapper.map)


def invoice_with_publication(publication_id: PublicationId) -> Invoice | None:
    invoice = InvoiceModel.objects.filter(positions__publication_id=publication_id).first()

    if not invoice:
        return None

    return InvoiceDomainMapper.map(invoice)


def invoice_number_of(invoice_id: InvoiceId) -> str:
    return InvoiceModel.objects.only("number").get(pk=invoice_id).number


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
