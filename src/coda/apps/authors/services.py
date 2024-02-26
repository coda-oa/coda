from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author, Person
from coda.apps.institutions.models import Institution


def author_create(dto: AuthorDto) -> Author:
    p = Person.objects.filter(name=dto["name"], email=dto["email"], orcid=dto["orcid"]).first()
    if p is None:
        p = Person.objects.create(name=dto["name"], email=dto["email"], orcid=dto["orcid"])
        p.full_clean()

    affiliation_pk = dto.get("affiliation")
    if affiliation_pk:
        affiliation = Institution.objects.get(pk=affiliation_pk)
    else:
        affiliation = None

    return Author.objects.create(details=p, affiliation=affiliation)
