from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, Person
from coda.apps.institutions.models import Institution


def create(dto: AuthorDto, affiliation: Institution | None) -> Author:
    p, _ = Person.objects.get_or_create(name=dto["name"], email=dto["email"], orcid=dto["orcid"])
    return Author.objects.create(details=p, affiliation=affiliation)
