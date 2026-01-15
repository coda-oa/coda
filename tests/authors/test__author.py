from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId
from coda.apps.authors.services import (
    as_domain_object,
    author_create,
    author_update,
    create_many_with_publications,
    get_by_id,
)
from coda.apps.institutions.models import Institution
from coda.domain.author import Author, InstitutionId
from coda.domain.orcid import Orcid
from coda.domain.publication import PublicationId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory, test_orcid

JOSIAHS_DATA = Author.new(
    name=NonEmptyStr("Josiah Carberry"),
    email="j.carberry@example.com",
    orcid=Orcid(test_orcid.JOSIAH_CARBERRY),
)


@pytest.mark.django_db
def test__can_create_author_with_empty_orcid() -> None:
    no_orcid = Author.new(JOSIAHS_DATA.name, JOSIAHS_DATA.email, orcid=None)
    new_id = author_create(no_orcid)

    actual = get_by_id(new_id)
    assert_author_eq(actual, no_orcid)


@pytest.mark.django_db
def test__orcids_must_be_unique() -> None:
    person1 = PersonId(
        orcid=f"https://orcid.org/{test_orcid.JOSIAH_CARBERRY}",
    )
    person1.full_clean()
    person1.save()

    with pytest.raises(ValidationError):
        person2 = PersonId(orcid=f"https://orcid.org/{test_orcid.JOSIAH_CARBERRY}")
        person2.full_clean()
        person2.save()


@pytest.mark.django_db
def test__updating_author__saves_updated_author_to_db() -> None:
    new_id = author_create(domainfactory.author())

    affiliation = modelfactory.institution()
    new_author = domainfactory.author(InstitutionId(affiliation.pk), id=new_id)

    author_update(new_author)

    actual = get_by_id(new_id)
    assert_author_eq(actual, new_author)


@pytest.mark.django_db
def test__can_update_author_with_existing_orcid() -> None:
    existing = domainfactory.author()
    existing.orcid = Orcid(test_orcid.JOSIAH_CARBERRY)
    author_create(existing)

    another = domainfactory.author()
    new_id = author_create(another)

    another.id = new_id
    another.orcid = Orcid(test_orcid.JOSIAH_CARBERRY)

    author_update(another)

    assert get_by_id(new_id).orcid == Orcid(test_orcid.JOSIAH_CARBERRY)


@pytest.mark.django_db
def test__updating_author__without_id__raises_error() -> None:
    author = domainfactory.author()
    author_create(author)

    new_author = domainfactory.author(id=None)
    with pytest.raises(ValidationError):
        author_update(new_author)


@pytest.mark.django_db
def test__details_already_exist__reuses_existing_person(client: Client) -> None:
    author_create(JOSIAHS_DATA)

    form_data = AuthorDto.from_author(JOSIAHS_DATA)
    form_data.affiliation = None
    client.post("/authors/create/", form_data.to_post_data())

    assert PersonId.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__given_institution_exits__when_author_is_affiliated__author_is_saved_with_affiliation(
    client: Client,
) -> None:
    institution = Institution(name="Brown University")
    institution.save()

    affiliation = institution.pk
    josiah = AuthorDto.from_author(JOSIAHS_DATA)
    josiah.affiliation = InstitutionId(affiliation)

    client.post("/authors/create/", josiah.to_post_data())

    author = as_domain_object(cast(AuthorModel, AuthorModel.objects.first()))
    assert author.affiliation == affiliation


@pytest.mark.django_db
def test__create_many_with_publications__creates_all_authors_with_correct_publications() -> None:
    """Multiple authors across multiple publications are created with correct publication_ids."""
    # Setup: Create 2 publications
    pub1 = modelfactory.publication(title="Publication 1")
    pub2 = modelfactory.publication(title="Publication 2")
    pub_id_1 = PublicationId(pub1.pk)
    pub_id_2 = PublicationId(pub2.pk)

    # Setup: 3 authors across 2 publications
    author1 = domainfactory.author()
    author2 = domainfactory.author()
    author3 = domainfactory.author()

    authors_with_pubs = [
        (author1, pub_id_1),
        (author2, pub_id_1),
        (author3, pub_id_2),
    ]

    # Execute
    ids = create_many_with_publications(authors_with_pubs)

    # Assert: All authors created
    assert len(ids) == 3
    assert AuthorModel.objects.count() == 3

    # Assert: Correct publication assignments
    author1_model = AuthorModel.objects.get(pk=ids[0])
    author2_model = AuthorModel.objects.get(pk=ids[1])
    author3_model = AuthorModel.objects.get(pk=ids[2])

    assert author1_model.publication_id == pub_id_1
    assert author2_model.publication_id == pub_id_1
    assert author3_model.publication_id == pub_id_2

    # Assert: PersonIDs created (one per author without ORCID)
    assert PersonId.objects.count() == 3


@pytest.mark.django_db
def test__create_many_with_publications__deduplicates_orcids_across_publications() -> None:
    """When multiple authors across different publications share an ORCID, they share the same PersonID."""
    # Setup: Create 3 publications
    pub1 = modelfactory.publication(title="Publication 1")
    pub2 = modelfactory.publication(title="Publication 2")
    pub3 = modelfactory.publication(title="Publication 3")
    pub_id_1 = PublicationId(pub1.pk)
    pub_id_2 = PublicationId(pub2.pk)
    pub_id_3 = PublicationId(pub3.pk)

    # Setup: Authors with shared and unique ORCIDs
    author_a = domainfactory.author()
    author_a.orcid = Orcid(test_orcid.JOSIAH_CARBERRY)  # ORCID X

    author_b = domainfactory.author()
    author_b.orcid = Orcid(test_orcid.JOSIAH_CARBERRY)  # ORCID X (same as author_a)

    author_c = domainfactory.author()
    author_c.orcid = Orcid("https://orcid.org/0000-0000-0000-0001")  # ORCID Y (unique)

    author_d = domainfactory.author()  # No ORCID

    authors_with_pubs = [
        (author_a, pub_id_1),  # Pub 1: ORCID X
        (author_b, pub_id_2),  # Pub 2: ORCID X (should share PersonID with author_a)
        (author_c, pub_id_3),  # Pub 3: ORCID Y
        (author_d, pub_id_1),  # Pub 1: No ORCID
    ]

    # Execute
    ids = create_many_with_publications(authors_with_pubs)

    # Assert: All authors created
    assert len(ids) == 4
    assert AuthorModel.objects.count() == 4

    # Assert: Only 3 PersonIDs created (X shared by 2 authors, Y unique, one without ORCID)
    assert PersonId.objects.count() == 3

    # Assert: Authors A and B share the same PersonID
    author_a_model = AuthorModel.objects.get(pk=ids[0])
    author_b_model = AuthorModel.objects.get(pk=ids[1])
    author_c_model = AuthorModel.objects.get(pk=ids[2])
    author_d_model = AuthorModel.objects.get(pk=ids[3])

    assert author_a_model.identifier_id == author_b_model.identifier_id  # Same PersonID
    assert author_a_model.identifier_id != author_c_model.identifier_id  # Different PersonID
    assert author_a_model.identifier_id != author_d_model.identifier_id  # Different PersonID

    # Assert: Correct ORCIDs
    shared_person_id = cast(PersonId, author_a_model.identifier)
    assert shared_person_id.orcid == test_orcid.JOSIAH_CARBERRY


@pytest.mark.django_db
def test__create_many_with_publications__handles_mixed_affiliations() -> None:
    """Authors with different institutions and no institution are created correctly."""
    # Setup: Two institutions
    inst_a = Institution(name="University A")
    inst_a.save()

    inst_b = Institution(name="University B")
    inst_b.save()

    # Setup: Create 2 publications
    pub1 = modelfactory.publication(title="Publication 1")
    pub2 = modelfactory.publication(title="Publication 2")
    pub_id_1 = PublicationId(pub1.pk)
    pub_id_2 = PublicationId(pub2.pk)

    # Authors with different affiliations
    author1 = domainfactory.author(InstitutionId(inst_a.pk))
    author2 = domainfactory.author(InstitutionId(inst_b.pk))
    author3 = domainfactory.author(None)  # No affiliation

    authors_with_pubs = [
        (author1, pub_id_1),
        (author2, pub_id_2),
        (author3, pub_id_1),
    ]

    # Execute
    ids = create_many_with_publications(authors_with_pubs)

    # Assert: All authors created with correct affiliations
    assert len(ids) == 3

    author1_model = AuthorModel.objects.get(pk=ids[0])
    author2_model = AuthorModel.objects.get(pk=ids[1])
    author3_model = AuthorModel.objects.get(pk=ids[2])

    assert author1_model.affiliation_id == inst_a.pk
    assert author2_model.affiliation_id == inst_b.pk
    assert author3_model.affiliation_id is None


def assert_author_eq(actual: Author, expected: Author) -> None:
    assert actual.name == expected.name
    assert actual.email == expected.email
    assert actual.affiliation == expected.affiliation
    assert actual.orcid == expected.orcid
