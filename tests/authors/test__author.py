from django.test import Client
import pytest
from django.core.exceptions import ValidationError

from coda.apps.authors.models import Author, Person
from tests import test_orcid


@pytest.mark.django_db
def test__cannot_create_person_with_empty_name() -> None:
    with pytest.raises(ValidationError):
        sut = Person(name="", email="john.doe@example.com")
        sut.full_clean()


@pytest.mark.django_db
def test__cannot_create_person_with_invalid_orcid() -> None:
    with pytest.raises(ValidationError):
        sut = Person(name="John Doe", email="john.doe@example.com", orcid="invalid")
        sut.full_clean()


@pytest.mark.django_db
def test__cannot_create_author_from_person_with_invalid_orcid() -> None:
    person = Person(name="John Doe", email="john.doe@example.com", orcid="invalid")

    with pytest.raises(ValidationError):
        sut = Author(details=person, affiliation=None)
        sut.full_clean()


@pytest.mark.django_db
def test__person_with_orcid_url__is_saved_with_pure_orcid() -> None:
    sut = Person(
        name="John Doe",
        email="john.doe@example.com",
        orcid=f"https://orcid.org/{test_orcid.JOSIAH_CARBERRY}",
    )
    sut.full_clean()

    assert sut.orcid == test_orcid.JOSIAH_CARBERRY


@pytest.mark.django_db
def test__orcids_must_be_unique() -> None:
    person1 = Person(
        name="Josiah Carberry",
        email="j.carberry@example.com",
        orcid=f"https://orcid.org/{test_orcid.JOSIAH_CARBERRY}",
    )
    person1.full_clean()
    person1.save()

    with pytest.raises(ValidationError):
        person2 = Person(
            name="Fake Josiah Carberry",
            email="j.carberry@fake.com",
            orcid=f"https://orcid.org/{test_orcid.JOSIAH_CARBERRY}",
        )
        person2.full_clean()
        person2.save()


@pytest.mark.django_db
def test__author_with_invalid_orcid__will_not_be_saved_to_db(client: Client) -> None:
    with pytest.raises(ValidationError):
        client.post(
            "/authors/create/",
            {"name": "John Doe", "email": "j.doe@example.com", "orcid": "invalid"},
        )

    assert Person.objects.count() == 0
    assert Author.objects.count() == 0
