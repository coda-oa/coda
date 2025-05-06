from typing import cast

from django.core.exceptions import ValidationError

from coda.apps.authors.models import Author as AuthorModel, deserialize_role
from coda.apps.authors.models import PersonId, serialize_role
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.domain.author import Author, AuthorId, InstitutionId
from coda.domain.orcid import Orcid
from coda.domain.publication import PublicationId
from coda.domain.string import NonEmptyStr


def first() -> Author | None:
    model = AuthorModel.objects.first()
    if model is None:
        return None

    return as_domain_object(model)


def get_by_id(author_id: AuthorId) -> Author:
    model = AuthorModel.objects.get(pk=author_id)
    return as_domain_object(model)


def as_domain_object(model: AuthorModel) -> Author:
    person_id = cast(PersonId, model.identifier)
    return Author(
        id=AuthorId(model.id),
        name=NonEmptyStr(model.name),
        email=model.email or "",
        orcid=Orcid(person_id.orcid) if person_id.orcid else None,
        affiliation=InstitutionId(model.affiliation.pk) if model.affiliation else None,
        role=deserialize_role(model.roles or ""),
    )


def author_create(author: Author, publication: PublicationId | None = None) -> AuthorId:
    affiliation = _find_affiliation(author.affiliation)
    if author.orcid:
        _id, _ = PersonId.objects.get_or_create(orcid=author.orcid)
    else:
        _id = PersonId.objects.create()

    roles = serialize_role(author.role)
    _author = AuthorModel.objects.create(
        name=author.name,
        email=author.email,
        identifier=_id,
        affiliation=affiliation,
        roles=roles,
        publication_id=publication,
    )
    return AuthorId(_author.id)


def create_many(authors: list[Author], publication: PublicationId | None = None) -> list[AuthorId]:
    person_ids = _assign_person_ids_for_authors(authors)
    affiliations = [_find_affiliation(a.affiliation) for a in authors]
    author_models = [
        AuthorModel(
            name=a.name,
            email=a.email,
            identifier=pid,
            affiliation=aff,
            roles=serialize_role(a.role),
            publication_id=publication,
        )
        for a, pid, aff in zip(authors, person_ids, affiliations)
    ]
    created = AuthorModel.objects.bulk_create(author_models)
    return [AuthorId(a.id) for a in created]


def _assign_person_ids_for_authors(authors: list[Author]) -> list[PersonId]:
    orcids = [a.orcid for a in authors if a.orcid]
    authors_without_orcid = [a for a in authors if not a.orcid]

    orcid_personids = _get_or_create_personids_by_orcid([orcid for orcid in orcids])
    no_orcid_personids = _bulk_create_personids_without_orcid(len(authors_without_orcid))

    # Assign PersonIds in order
    person_ids = []
    no_orcid_iter = iter(no_orcid_personids)
    for a in authors:
        if a.orcid:
            person_ids.append(orcid_personids[a.orcid])
        else:
            person_ids.append(next(no_orcid_iter))
    return person_ids


def _get_or_create_personids_by_orcid(authors_with_orcid: list[Orcid]) -> dict[Orcid, PersonId]:
    orcids = [orcid for orcid in authors_with_orcid]
    existing = {cast(Orcid, p.orcid): p for p in PersonId.objects.filter(orcid__in=orcids)}
    new_orcids = [o for o in orcids if o not in existing]
    if new_orcids:
        PersonId.objects.bulk_create([PersonId(orcid=o) for o in new_orcids], ignore_conflicts=True)
        existing.update(
            {cast(Orcid, p.orcid): p for p in PersonId.objects.filter(orcid__in=new_orcids)}
        )

    return existing


def _bulk_create_personids_without_orcid(count: int) -> list[PersonId]:
    if count == 0:
        return []
    PersonId.objects.bulk_create([PersonId() for _ in range(count)])
    objs = list(PersonId.objects.filter(orcid__isnull=True).order_by("-id")[:count])
    objs.reverse()
    return objs


def author_update(author: Author) -> Author:
    if not author.id:
        raise ValidationError("Author ID is required")

    model = AuthorModel.objects.get(pk=author.id)
    identifier = cast(PersonId, model.identifier)
    if author.orcid:
        existing = PersonId.objects.filter(orcid=author.orcid)
        if existing.exists():
            model.identifier = existing.get()
            model.identifier.save()
        else:
            identifier.orcid = author.orcid
            identifier.save()

    model.name = author.name
    model.email = author.email
    if author.affiliation:
        model.affiliation = _find_affiliation(author.affiliation)

    if author.role:
        model.roles = serialize_role(author.role)

    model.save()
    return author


def _find_affiliation(affiliation_pk: int | None) -> Institution | None:
    if affiliation_pk:
        affiliation = institution_repository.get_by_id(affiliation_pk)
    else:
        affiliation = None
    return affiliation
