from typing import cast

from django.core.exceptions import ValidationError

from coda.apps.authors.models import Author as AuthorModel, deserialize_roles
from coda.apps.authors.models import PersonId, serialize_roles
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.author import Author, AuthorId, InstitutionId
from coda.orcid import Orcid
from coda.string import NonEmptyStr


def get_by_id(author_id: AuthorId) -> Author:
    model = AuthorModel.objects.get(pk=author_id)
    return Author(
        id=author_id,
        name=NonEmptyStr(model.name),
        email=model.email or "",
        orcid=Orcid(model.identifier.orcid) if model.identifier else None,
        affiliation=InstitutionId(model.affiliation.pk) if model.affiliation else None,
        roles=frozenset(deserialize_roles(model.roles or "")),
    )


def author_create(author: Author) -> AuthorId:
    affiliation = _find_affiliation(author.affiliation)
    _id, _ = PersonId.objects.get_or_create(orcid=author.orcid)
    roles = serialize_roles(author.roles)
    _author = AuthorModel.objects.create(
        name=author.name, email=author.email, identifier=_id, affiliation=affiliation, roles=roles
    )
    return AuthorId(_author.id)


def author_update(author: Author) -> Author:
    if not author.id:
        raise ValidationError("Author ID is required")

    model = AuthorModel.objects.get(pk=author.id)
    identifier = cast(PersonId, model.identifier)
    identifier.orcid = author.orcid
    identifier.save()
    model.name = author.name
    model.email = author.email
    if author.affiliation:
        model.affiliation = _find_affiliation(author.affiliation)

    if author.roles:
        model.roles = serialize_roles(author.roles)

    model.save()
    return author


def _find_affiliation(affiliation_pk: int | None) -> Institution | None:
    if affiliation_pk:
        affiliation = institution_repository.get_by_id(affiliation_pk)
    else:
        affiliation = None
    return affiliation
