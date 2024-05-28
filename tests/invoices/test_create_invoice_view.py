import pytest
from django.test import Client

from coda.apps.invoices.models import Invoice
from tests import modelfactory


@pytest.mark.django_db
def test__completed_invoice_create_view__saves_invoice_to_db(client: Client) -> None:
    fr = modelfactory.fundingrequest()
    publisher_id = fr.publication.journal.publisher.id
    publication_id = fr.publication.id

    invoice_data = {"number": "123", "recipient": publisher_id}
    position = {"add_position": publication_id}

    client.post("/invoices/create/", invoice_data | position)

    assert Invoice.objects.count() == 1
