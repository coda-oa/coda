import datetime

import pytest

from coda.apps.invoices import repository
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.services import (
    can_delete_creditor,
    archive_creditor,
    restore_creditor,
    delete_creditor,
)
from coda.domain.finance.invoice import CreditorId, Invoice


@pytest.fixture
def creditor() -> Creditor:
    return Creditor.objects.create(name="Test Creditor")


def _create_invoice(creditor: Creditor) -> None:
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[],
    )
    repository.create(invoice)


@pytest.mark.django_db
def test__can_delete_creditor_with_no_invoices(creditor: Creditor) -> None:
    can_delete, blocking = can_delete_creditor(creditor)

    assert can_delete is True
    assert blocking == []


@pytest.mark.django_db
def test__cannot_delete_creditor_with_invoices(creditor: Creditor) -> None:
    _create_invoice(creditor)

    can_delete, blocking = can_delete_creditor(creditor)

    assert can_delete is False
    assert "1 invoice(s)" in blocking[0]


@pytest.mark.django_db
def test__cannot_delete_creditor_with_multiple_invoices(creditor: Creditor) -> None:
    _create_invoice(creditor)
    _create_invoice(creditor)

    can_delete, blocking = can_delete_creditor(creditor)

    assert can_delete is False
    assert "2 invoice(s)" in blocking[0]


@pytest.mark.django_db
def test__archive_creditor__sets_archived_at(creditor: Creditor) -> None:
    archive_creditor(creditor)

    creditor.refresh_from_db()
    assert creditor.archived_at is not None


@pytest.mark.django_db
def test__archive_creditor__raises_error_if_already_archived(creditor: Creditor) -> None:
    archive_creditor(creditor)

    with pytest.raises(ValueError, match="Creditor is already archived"):
        archive_creditor(creditor)


@pytest.mark.django_db
def test__restore_creditor__clears_archived_at(creditor: Creditor) -> None:
    archive_creditor(creditor)

    restore_creditor(creditor)

    creditor.refresh_from_db()
    assert creditor.archived_at is None


@pytest.mark.django_db
def test__restore_creditor__raises_error_if_not_archived(creditor: Creditor) -> None:
    with pytest.raises(ValueError, match="Creditor is not archived"):
        restore_creditor(creditor)


@pytest.mark.django_db
def test__delete_creditor_with_no_invoices__deletes(creditor: Creditor) -> None:
    delete_creditor(creditor)

    assert not Creditor.all_objects.filter(pk=creditor.pk).exists()


@pytest.mark.django_db
def test__delete_creditor_with_invoices__raises_error(creditor: Creditor) -> None:
    _create_invoice(creditor)

    with pytest.raises(ValueError, match="Cannot delete creditor"):
        delete_creditor(creditor)

    assert Creditor.all_objects.filter(pk=creditor.pk).exists()
