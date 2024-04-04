import datetime

from coda.apps.authors.models import Author
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.models import Link, LinkType, Publication


def create(publication: PublicationDto, author: Author, journal: Journal) -> Publication:
    _publication = Publication.objects.create(
        title=publication["title"],
        publication_state=publication["publication_state"],
        publication_date=datetime.date.fromisoformat(publication["publication_date"]),
        submitting_author=author,
        journal=journal,
    )

    attach_links(_publication, publication["links"])
    return _publication


def attach_links(publication: Publication, links: list[LinkDto]) -> None:
    publication.links.all().delete()
    Link.objects.bulk_create(
        [
            Link(
                value=link["link_value"],
                type=LinkType.objects.get(pk=link["link_type"]),
                publication=publication,
            )
            for link in links
        ]
    )
