from coda.apps.authors.dto import AuthorDto
from coda.apps.institutions import repository as institution_repository
from coda.domain.author import InstitutionId

from ..dto import AuthorImportDto


def parse_dto(import_dto: AuthorImportDto) -> AuthorDto:
    affiliation = _parse_affiliation(import_dto)
    return AuthorDto(
        name=import_dto.name,
        email=import_dto.email,
        orcid=import_dto.orcid,
        role=import_dto.role.name,
        affiliation=affiliation,
    )


def _parse_affiliation(import_dto: AuthorImportDto) -> InstitutionId | None:
    if import_dto.affiliation is None:
        return None

    institution = institution_repository.first_by_name(import_dto.affiliation)
    if not institution:
        institution = institution_repository.create(import_dto.affiliation)

    return InstitutionId(institution.id)
