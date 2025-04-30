import pytest

from coda.apps.publications.models import PublicationPayment
from tests import modelfactory


@pytest.mark.django_db
def test__publication_with_payment__delete_publication__deletes_payment() -> None:
    p = modelfactory.publication()
    payment = PublicationPayment.objects.create(status="paid", publication=p)

    p.delete()

    assert not PublicationPayment.objects.filter(id=payment.id).exists()


@pytest.mark.django_db
def test__publication_with_invoice__delete_publication__deletes_position() -> None:
    p = modelfactory.publication()
    invoice = modelfactory.invoice()
    position = invoice.positions.create(publication=p, cost_amount=100, cost_currency="EUR")

    p.delete()

    assert not invoice.positions.filter(id=position.id).exists()
