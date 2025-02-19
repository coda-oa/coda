from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.fundingrequests.wizard.wizardsubmitter import (
    complete_early_iterator,
    monograph_wizardsubmitter,
    update_monograph_publication_wizard,
)

BuilderFactory = Callable[[], MonographRequestDataBuilder]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
@pytest.mark.parametrize(
    "get_builder",
    [
        lambda: MonographRequestDataBuilder(),
        lambda: MonographRequestDataBuilder().with_empty_contact(),
    ],
    ids=["filled_contact", "empty_contact"],
)
def test__completing_monograph_wizard__creates_funding_request_for_monograph_and_shows_details(
    client: Client, get_builder: BuilderFactory
) -> None:
    builder = get_builder()
    wizard = monograph_wizardsubmitter(client, builder)
    response = wizard.submit_all()

    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, builder.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__updating_monograph_meta_step__saves_fundingrequest_with_changed_data(
    client: Client,
) -> None:
    builder = MonographRequestDataBuilder()
    id = repository.save(builder.build())

    monograph = repository.get_monograph_request(id)
    updated = builder.with_new_publication(monograph.publication.id)

    wizard = update_monograph_publication_wizard(client, id, updated)
    response = wizard.submit_all()

    actual = repository.get_monograph_request(id)
    assert_fundingrequest_eq(actual, updated.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__updating_monograph_meta_step__completed_early__saves_fundingrequest_with_changed_data(
    client: Client,
) -> None:
    builder = MonographRequestDataBuilder()
    id = repository.save(builder.build())

    monograph = repository.get_monograph_request(id)
    updated = (
        builder.with_new_publication(id=monograph.publication.id)
        .with_contracts(monograph.publication.contracts)
        .with_publisher(monograph.publication.publisher)
    )

    wizard = update_monograph_publication_wizard(client, id, updated)
    wizard.step_iterator = complete_early_iterator(until=0)
    response = wizard.submit_all()

    actual = repository.get_monograph_request(id)
    assert_fundingrequest_eq(actual, updated.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": id}))
