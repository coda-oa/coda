import datetime
from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import Publication


def create(publication: PublicationDto, author: Author, journal: Journal) -> Publication:
    return Publication.objects.create(
        title=publication["title"],
        publication_state=publication["publication_state"],
        publication_date=datetime.date.fromisoformat(publication["publication_date"]),
        submitting_author=author,
        journal=journal,
    )
