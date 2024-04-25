from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from coda.apps.authors.dto import parse_author
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.models import PersonId
from coda.apps.authors.services import author_create, author_update
from coda.apps.institutions.models import Institution
from coda.author import Author, AuthorId, Role
from coda.orcid import Orcid
from coda.string import NonEmptyStr
from tests import factory, test_orcid
from tests.assertions import assert_author_equal

JOSIAHS_DATA = Author(
    id=None,
    name=NonEmptyStr("Josiah Carberry"),
    email="j.carberry@example.com",
    orcid=Orcid(test_orcid.JOSIAH_CARBERRY),
)


@pytest.mark.django_db
def test__can_create_author_with_empty_orcid() -> None:
    no_orcid = Author(None, JOSIAHS_DATA.name, JOSIAHS_DATA.email, orcid=None)
    author_create(no_orcid)


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
def test__adding_roles_to_author__saves_roles_to_db() -> None:
    josiah = Author(
        None,
        JOSIAHS_DATA.name,
        JOSIAHS_DATA.email,
        roles=frozenset({Role.SUBMITTER, Role.CO_AUTHOR}),
    )

    author_create(josiah)

    author = cast(AuthorModel, AuthorModel.objects.first())
    assert Role.SUBMITTER.name in cast(str, author.roles)
    assert Role.CO_AUTHOR.name in cast(str, author.roles)


@pytest.mark.django_db
def test__updating_author__saves_updated_author_to_db() -> None:
    author = factory.db_author()

    affiliation = factory.db_institution()
    new_author_data = factory.author_dto(affiliation.pk)
    new_author = parse_author(new_author_data, id=AuthorId(author.pk))

    author_update(new_author)

    author.refresh_from_db()
    assert_author_equal(new_author_data, author)


@pytest.mark.django_db
def test__updating_author__without_id__raises_error() -> None:
    _ = factory.db_author()

    new_author_data = factory.author_dto()
    new_author = parse_author(new_author_data, id=None)

    with pytest.raises(ValidationError):
        author_update(new_author)


@pytest.mark.django_db
def test__details_already_exist__reuses_existing_person(client: Client) -> None:
    author_create(JOSIAHS_DATA)

    form_data = JOSIAHS_DATA._asdict()
    form_data.pop("id")
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
    josiah = JOSIAHS_DATA._asdict()
    josiah["affiliation"] = affiliation
    josiah.pop("id")

    client.post("/authors/create/", josiah)

    author = cast(AuthorModel, AuthorModel.objects.first())
    assert author.affiliation == institution
