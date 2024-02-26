from coda import orcid
from coda.apps.authors import repository as author_repository
from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.validation import as_validator

orcid_validator = as_validator(orcid.parse)


@as_validator
def author_create(dto: AuthorDto) -> Author:
    if not dto["name"]:
        raise ValueError("Author name is required")

    dto["orcid"] = orcid_validator(dto.get("orcid"))

    affiliation = _find_affiliation(dto)
    return author_repository.create(dto, affiliation)


def _find_affiliation(dto: AuthorDto) -> Institution | None:
    affiliation_pk = dto.get("affiliation")
    if affiliation_pk:
        affiliation = institution_repository.get_by_id(affiliation_pk)
    else:
        affiliation = None
    return affiliation
