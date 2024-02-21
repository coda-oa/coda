import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.models import AuthorDto
from coda.apps.institutions.models import Institution
from tests import test_orcid


def institution() -> Institution:
    return Institution.objects.create(name="Test Institution")


def valid_author(affiliation_pk: int) -> AuthorDto:
    return AuthorDto(
        name="Josiah Carberry",
        email="carberry@example.com",
        orcid=test_orcid.JOSIAH_CARBERRY,
        affiliation=affiliation_pk,
    )


def invalid_orcid_author(affiliation_pk: int) -> AuthorDto:
    author = valid_author(affiliation_pk)
    author["orcid"] = "invalid"
    return author


@pytest.mark.django_db
def test__fundingrequest_wizard__first_step__when_valid_data__stores_data_in_session_and_redirects_to_next_step(
    client: Client,
) -> None:
    affiliation = institution()

    form_data = valid_author(affiliation.pk)
    response = client.post(reverse("fundingrequests:create"), form_data)

    assert client.session["submitter"] == form_data
    assertRedirects(response, reverse("fundingrequests:create_publication"))
