from coda.apps.authors.models import Author
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto, parse_publication
from coda.apps.publications.models import Link, LinkType, Publication
from coda.publication import Published


def publication_create(
    publication: PublicationDto, author: Author, journal: Journal
) -> Publication:
    p = parse_publication(publication)
    publication_date = None
    if isinstance(p.publication_state, Published):
        publication_date = p.publication_state.date

    journal = Journal.objects.get(pk=p.journal)
    _publication = Publication.objects.create(
        title=p.title,
        license=p.license.name,
        open_access_type=p.open_access_type.name,
        publication_state=p.publication_state.name(),
        publication_date=publication_date,
        submitting_author=author,
        author_list=str(p.authors),
        journal=journal,
    )

    _attach_links(_publication, publication["links"])
    return _publication


def publication_update(publication: Publication, publication_dto: PublicationDto) -> None:
    publication.title = publication_dto["title"]
    publication.author_list = str(publication_dto["authors"])
    publication.license = publication_dto["license"]
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
                type=LinkType.objects.get(name=link["link_type"]),
                publication=publication,
            )
            for link in links
        ]
    )
