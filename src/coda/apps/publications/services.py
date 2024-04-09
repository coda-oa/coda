import datetime

from coda.apps.authors.models import Author
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.models import Link, LinkType, Publication


def create(publication: PublicationDto, author: Author, journal: Journal) -> Publication:
    _publication = Publication.objects.create(
        title=publication["title"],
        open_access_type=publication["open_access_type"],
        publication_state=publication["publication_state"],
        publication_date=datetime.date.fromisoformat(publication["publication_date"]),
        submitting_author=author,
        journal=journal,
    )

    _attach_links(_publication, publication["links"])
    return _publication


def publication_update(publication: Publication, publication_dto: PublicationDto) -> None:
    publication.title = publication_dto["title"]
    publication.open_access_type = publication_dto["open_access_type"]
    publication.journal = journal_services.get_by_pk(publication_dto["journal"])
    publication.publication_state = publication_dto["publication_state"]
    publication.publication_date = publication_dto["publication_date"]
    _attach_links(publication, publication_dto["links"])
    publication.save()


def _attach_links(publication: Publication, links: list[LinkDto]) -> None:
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
