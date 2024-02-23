import datetime
from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import Publication


def create(author: AuthorDto, publication: PublicationDto, funding: FundingDto) -> FundingRequest:
    _author = Author.create_from_dto(author)
    journal = Journal.objects.get(pk=publication["journal"])
    _publication = Publication.objects.create(
        title=publication["title"],
        publication_state=publication["publication_state"],
        publication_date=datetime.date.fromisoformat(publication["publication_date"]),
        submitting_author=_author,
        journal=journal,
    )

    return FundingRequest.objects.create(submitter=_author, publication=_publication, **funding)
