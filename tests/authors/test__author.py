from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from coda.apps.authors.dto import AuthorDto

from coda.apps.authors.models import Author, PersonId
from coda.apps.authors.services import author_create
from coda.apps.institutions.models import Institution
from tests import test_orcid

JOSIAHS_DATA = {
    "name": "Josiah Carberry",
    "email": "j.carberry@example.com",
    "orcid": test_orcid.JOSIAH_CARBERRY,
    "affiliation": None,
}


@pytest.mark.django_db
def test__cannot_create_author_with_empty_name() -> None:
    with pytest.raises(ValidationError):
        no_name = JOSIAHS_DATA.copy()
        no_name["name"] = ""
        author_create(no_name)


@pytest.mark.django_db
def test__cannot_create_author_with_invalid_orcid() -> None:
    with pytest.raises(ValidationError):
        dto = AuthorDto(
            name="John Doe", email="john.doe@example.com", orcid="invalid", affiliation=None
        )
        author_create(dto)


@pytest.mark.django_db
def test__author_with_orcid_url__is_saved_with_pure_orcid() -> None:
    josiah = JOSIAHS_DATA.copy()
    josiah["orcid"] = f"https://orcid.org/{josiah['orcid']}"

    author_create(josiah)

    author = cast(Author, Author.objects.first())
    assert author.identifier is not None
    assert author.identifier.orcid == josiah["orcid"]


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
def test__author_with_invalid_orcid__will_not_be_saved_to_db(client: Client) -> None:
    institution = Institution.objects.create(name="The Institution")

    client.post(
        "/authors/create/",
        {
            "name": "John Doe",
            "email": "j.doe@example.com",
            "orcid": "invalid",
            "affiliation": institution.pk,
        },
    )

    assert PersonId.objects.count() == 0
    assert Author.objects.count() == 0


@pytest.mark.django_db
def test__details_already_exist__reuses_existing_person(client: Client) -> None:
    author_create(JOSIAHS_DATA)

    form_data = JOSIAHS_DATA.copy()
    form_data["affiliation"] = ""
    client.post("/authors/create/", form_data)

    assert PersonId.objects.count() == 1


@pytest.mark.django_db
def test__given_institution_exits__when_author_is_affiliated__author_is_saved_with_affiliation(
    client: Client,
) -> None:
    institution = Institution(name="Brown University")
    institution.save()

    affiliation = institution.pk
    josiah = JOSIAHS_DATA.copy()
    josiah["affiliation"] = str(affiliation)

    client.post("/authors/create/", josiah)

    author = cast(Author, Author.objects.first())
    assert author.affiliation == institution
