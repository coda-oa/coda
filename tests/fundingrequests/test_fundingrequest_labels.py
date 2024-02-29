import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.services import fundingrequest_create, label_attach, label_create
from coda.apps.users.models import User
from coda.color import Color
from tests.fundingrequests import factory


@pytest.fixture
def logged_in(client: Client) -> None:
    client.force_login(User.objects.create_user("testuser"))


@pytest.mark.django_db
def test__creating_a_label__stores_it_in_the_database() -> None:
    red = Color.from_rgb(255, 0, 0)
    label = label_create("My label", red)

    assert Label.objects.first() == label
    assert label.name == "My label"
    assert label.hexcolor == red.hex()


@pytest.mark.django_db
def test__attach_label__stores_label_in_funding_request() -> None:
    funding_request = fundingrequest_create(
        factory.valid_author_dto(factory.institution().pk),
        factory.publication_dto(factory.journal().pk),
        factory.funding_dto(),
    )

    label = label_create("My label", Color.from_rgb(255, 0, 0))
    label_id = label.pk
    label_attach(funding_request, label_id)

    assert funding_request.labels.first() == label


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_attach_label_view__can_attach_label_to_funding_request(
    client: Client,
) -> None:
    funding_request = fundingrequest_create(
        factory.valid_author_dto(factory.institution().pk),
        factory.publication_dto(factory.journal().pk),
        factory.funding_dto(),
    )
    label = label_create("My label", Color.from_rgb(255, 0, 0))

    post_data = {"fundingrequest": funding_request.pk, "label": label.pk}
    response = client.post(reverse("fundingrequests:label_attach"), post_data)

    kwargs = {"pk": funding_request.pk}
    assertRedirects(response, reverse("fundingrequests:detail", kwargs=kwargs))
    assert funding_request.labels.first() == label
