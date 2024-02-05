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
        sut = Author(details=person)
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
