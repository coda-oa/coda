from django.core.management import BaseCommand
from coda.apps.publications.repositories import publication_repository
from tests import domainfactory, modelfactory

from coda.apps.invoices import services
from coda.invoice import CreditorId
from coda.money import Currency
from coda.publication import JournalId, PublicationId


class Command(BaseCommand):
    help = "Add test invoices"

    def handle(self, *args: str, **options: str) -> None:
        publisher_id = modelfactory.publisher().id
        creditor_id = CreditorId(modelfactory.creditor().id)
        publications = [random_publication(publisher_id) for _ in range(3)]
        invoice = domainfactory.invoice(
            creditor=creditor_id,
            positions=[
                domainfactory.publication_position(publication=publication, currency=Currency.EUR)
                for i, publication in enumerate(publications, start=1)
            ],
        )

        services.save(invoice)


def random_publication(publisher_id: int) -> PublicationId:
    journal_id = modelfactory.journal(publisher_id).id
    return publication_repository.save(domainfactory.publication(journal=JournalId(journal_id)))
