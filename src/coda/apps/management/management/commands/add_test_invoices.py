from django.core.management import BaseCommand
from tests import domainfactory, modelfactory

from coda.apps.authors.services import author_create
from coda.apps.invoices import services
from coda.apps.publications.services import publication_create
from coda.invoice import CreditorId
from coda.money import Currency
from coda.publication import JournalId, PublicationId


class Command(BaseCommand):
    help = "Add test invoices"

    def handle(self, *args: str, **options: str) -> None:
        publisher_id = modelfactory.publisher().id
        publications = [random_publication(publisher_id) for _ in range(3)]
        invoice = domainfactory.invoice(
            creditor=CreditorId(publisher_id),
            positions=[
                domainfactory.publication_position(publication=publication, currency=Currency.EUR)
                for i, publication in enumerate(publications, start=1)
            ],
        )

        services.invoice_create(invoice)


def random_publication(publisher_id: int) -> PublicationId:
    journal_id = modelfactory.journal(publisher_id).id
    author_id = author_create(domainfactory.author())
    return publication_create(domainfactory.publication(journal=JournalId(journal_id)), author_id)
