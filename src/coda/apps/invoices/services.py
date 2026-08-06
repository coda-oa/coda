from coda.apps.invoices.models import Creditor, Invoice


def can_delete_creditor(creditor: Creditor) -> tuple[bool, list[str]]:
    blocking: list[str] = []
    invoice_count = Invoice.objects.filter(creditor=creditor).count()
    if invoice_count > 0:
        blocking.append(f"{invoice_count} invoice(s) reference this creditor")
    return len(blocking) == 0, blocking


def archive_creditor(creditor: Creditor) -> None:
    if creditor.archived_at:
        raise ValueError("Creditor is already archived")
    creditor.archive()


def restore_creditor(creditor: Creditor) -> None:
    if not creditor.archived_at:
        raise ValueError("Creditor is not archived")
    creditor.restore()


def delete_creditor(creditor: Creditor) -> None:
    can_delete, reasons = can_delete_creditor(creditor)
    if not can_delete:
        raise ValueError(f"Cannot delete creditor: {', '.join(reasons)}")
    creditor.delete()
