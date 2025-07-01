import pytest

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.models import Publication, PublicationPayment
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


@pytest.mark.django_db
def test__publication__delete_publication__deletes_fundingrequest() -> None:
    fundingrequest = modelfactory.fundingrequest()
    publication = fundingrequest.publication

    publication.delete()

    assert not FundingRequest.objects.filter(id=fundingrequest.id).exists()


@pytest.mark.django_db
def test__fundingrequest__delete_fundingrequest__deletes_publication() -> None:
    fundingrequest = modelfactory.fundingrequest()
    publication_id = fundingrequest.publication.id

    fundingrequest.delete()

    assert not Publication.objects.filter(id=publication_id).exists()


@pytest.mark.django_db
def test__fundingrequest_manager__delete__deletes_publication() -> None:
    fundingrequest = modelfactory.fundingrequest()
    publication_id = fundingrequest.publication.id

    FundingRequest.objects.all().delete()

    assert not Publication.objects.filter(id=publication_id).exists()
