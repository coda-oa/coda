from typing import cast

from django.core.exceptions import ValidationError

from coda.apps.authors.mappers import AuthorDomainMapper
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId, serialize_role
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.domain.author import Author, AuthorId, InstitutionId
from coda.domain.orcid import Orcid
from coda.domain.publication import PublicationId


def first() -> Author | None:
    model = AuthorDomainMapper.prefetch(AuthorModel.objects.all()).first()
    if model is None:
        return None

    return AuthorDomainMapper.map(model)


def get_by_id(author_id: AuthorId) -> Author:
    model = AuthorModel.objects.get(pk=author_id)
    return AuthorDomainMapper.map(model)


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
    return AuthorId(_author.pk)


def create_many(authors: list[Author], publication: PublicationId | None = None) -> list[AuthorId]:
    person_ids = _assign_person_ids_for_authors(authors)

    # Bulk fetch all institutions in one query instead of N queries
    affiliation_ids = {a.affiliation for a in authors if a.affiliation}
    affiliations_map: dict[InstitutionId, Institution] = {}
    if affiliation_ids:
        institutions = Institution.objects.filter(pk__in=affiliation_ids)
        affiliations_map = {InstitutionId(inst.pk): inst for inst in institutions}

    # Map affiliations to authors (None stays None, IDs are looked up)
    affiliations = [affiliations_map.get(a.affiliation) if a.affiliation else None for a in authors]

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
    return [AuthorId(a.pk) for a in created]


def create_many_with_publications(
    authors_with_pubs: list[tuple[Author, PublicationId]],
) -> list[AuthorId]:
    """Create multiple authors across different publications in one bulk operation.

    Optimized for bulk imports where authors from many publications need to be
    created together. Each author is created with its publication_id set.

    Args:
        authors_with_pubs: List of (Author, PublicationId) tuples. Each author
                          will be created with the corresponding publication_id.

    Returns:
        List of created AuthorIds in the same order as input.

    Example:
        # Create authors for 2 publications in one operation
        authors_with_pubs = [
            (author1, pub_id_1),  # Author for publication 1
            (author2, pub_id_1),  # Another author for publication 1
            (author3, pub_id_2),  # Author for publication 2
        ]
        ids = create_many_with_publications(authors_with_pubs)
        # Result: 3 authors created, each with correct publication_id
    """
    if not authors_with_pubs:
        return []

    # Separate authors and their publication IDs
    authors = [author for author, _ in authors_with_pubs]
    pub_ids = [pub_id for _, pub_id in authors_with_pubs]

    # Assign PersonIDs for ALL authors (handles ORCID de-duplication)
    person_ids = _assign_person_ids_for_authors(authors)

    # Bulk fetch ALL unique institutions in one query
    affiliation_ids = {a.affiliation for a in authors if a.affiliation}
    affiliations_map: dict[InstitutionId, Institution] = {}
    if affiliation_ids:
        institutions = Institution.objects.filter(pk__in=affiliation_ids)
        affiliations_map = {InstitutionId(inst.pk): inst for inst in institutions}

    # Map institutions to authors (None if no affiliation)
    affiliations = [affiliations_map.get(a.affiliation) if a.affiliation else None for a in authors]

    # Bulk create ALL author models with their publication_ids
    author_models = [
        AuthorModel(
            name=a.name,
            email=a.email,
            identifier=person_id,
            affiliation=affiliation,
            roles=serialize_role(a.role),
            publication_id=pub_id,
        )
        for a, person_id, affiliation, pub_id in zip(authors, person_ids, affiliations, pub_ids)
    ]

    # Single bulk create for all authors across all publications
    created = AuthorModel.objects.bulk_create(author_models)
    return [AuthorId(a.pk) for a in created]


def _assign_person_ids_for_authors(authors: list[Author]) -> list[PersonId]:
    orcids = [a.orcid for a in authors if a.orcid]
    authors_without_orcid = [a for a in authors if not a.orcid]

    orcid_personids = _get_or_create_personids_by_orcid([orcid for orcid in orcids])
    no_orcid_personids = _bulk_create_personids_without_orcid(len(authors_without_orcid))

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
    """Create PersonIds without ORCID in bulk.

    Django's bulk_create() returns the created objects with IDs set (on PostgreSQL),
    eliminating the need for a second query that would fetch all PersonIds without
    ORCID from the database (which could be hundreds of thousands of records).

    Args:
        count: Number of PersonIds to create

    Returns:
        List of created PersonId objects in creation order
    """
    if count == 0:
        return []

    person_ids = PersonId.objects.bulk_create([PersonId() for _ in range(count)])
    return list(person_ids)


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
