from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, PersonId
from coda.apps.institutions.models import Institution


def create(dto: AuthorDto, affiliation: Institution | None) -> Author:
    _id, _ = PersonId.objects.get_or_create(orcid=dto["orcid"])
    return Author.objects.create(
        name=dto["name"], email=dto["email"], identifier=_id, affiliation=affiliation
    )
