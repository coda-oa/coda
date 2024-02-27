import datetime

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import Link, LinkType, Publication


def create(publication: PublicationDto, author: Author, journal: Journal) -> Publication:
    _publication = Publication.objects.create(
        title=publication["title"],
        publication_state=publication["publication_state"],
        publication_date=datetime.date.fromisoformat(publication["publication_date"]),
        submitting_author=author,
        journal=journal,
    )

    _attach_links(publication, _publication)
    return _publication


def _attach_links(publication: PublicationDto, _publication: Publication) -> None:
    Link.objects.bulk_create(
        [
            Link(
                value=link["value"],
                type=LinkType.objects.get(pk=link["link_type_id"]),
                publication=_publication,
            )
            for link in publication["links"]
        ]
    )
