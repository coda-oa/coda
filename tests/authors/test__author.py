from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId
from coda.apps.authors.services import as_domain_object, author_create, author_update, get_by_id
from coda.apps.institutions.models import Institution
from coda.domain.author import Author, InstitutionId
from coda.domain.orcid import Orcid
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


def assert_author_eq(actual: Author, expected: Author) -> None:
    assert actual.name == expected.name
    assert actual.email == expected.email
    assert actual.affiliation == expected.affiliation
    assert actual.orcid == expected.orcid
