from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.users.models import User
from coda.fundingrequest import FundingRequestId
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.wizardsubmitter import (
    article_wizardsubmitter,
    complete_early_iterator,
    update_article_publication_wizard,
    update_extra_information_wizard,
    update_funding_wizard,
)
from tests.publications.test_publication_repository import assert_publication_eq


@pytest.fixture(autouse=True)
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


def save_new_fundingrequest() -> FundingRequestId:
    fr = ArticleRequestDataBuilder().expected
    fr_id = repository.save(fr)
    return fr_id


BuilderFactory = Callable[[], ArticleRequestDataBuilder]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "get_builder",
    [
        lambda: ArticleRequestDataBuilder(),
        lambda: ArticleRequestDataBuilder().with_empty_contact(),
    ],
    ids=["filled_contact", "empty_contact"],
)
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details___new(
    client: Client, get_builder: BuilderFactory
) -> None:
    builder = get_builder()
    submitter = article_wizardsubmitter(client, builder)

    response = submitter.submit_all()

    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, builder.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
def test__updating_fundingrequest_extra_information__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    builder = ArticleRequestDataBuilder()
    fr_id = repository.save(builder.expected)

    builder = builder.with_new_contact().with_new_request_remarks()
    wizard = update_extra_information_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    expected = builder.expected
    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_publication__updates_fundingrequest_and_shows_details(
    client: Client,
) -> None:
    existing_request_id = save_new_fundingrequest()
    builder = ArticleRequestDataBuilder()

    wizard = update_article_publication_wizard(client, existing_request_id, builder)
    response = wizard.submit_all()

    expected = builder.expected.publication
    actual = repository.get_by_id(existing_request_id).publication
    assert_publication_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": existing_request_id}))


@pytest.mark.django_db
def test__updating_only_publication_page_of_update_publication_wizard__saves_early(
    client: Client,
) -> None:
    existing_request_id = save_new_fundingrequest()
    existing_request = repository.get_article_request(existing_request_id)

    builder = (
        ArticleRequestDataBuilder()
        .with_contracts(existing_request.publication.contracts)
        .with_journal(existing_request.publication.journal)
    )

    wizard = update_article_publication_wizard(client, existing_request_id, builder)
    wizard.step_iterator = complete_early_iterator(until=0)

    wizard.submit_all()

    actual = repository.get_by_id(existing_request_id).publication
    assert_publication_eq(actual, builder.expected.publication)


@pytest.mark.django_db
def test__updating_fundingrequest_funding__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()
    fr_before_update = repository.get_by_id(fr_id)

    builder = ArticleRequestDataBuilder().with_payment(fr_before_update.estimated_cost)

    wizard = update_funding_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    fr = repository.get_by_id(fr_id)
    expected_payment = builder.expected.estimated_cost
    expected_funding = builder.expected.external_funding
    assert fr.estimated_cost == expected_payment
    assert list(fr.external_funding) == list(expected_funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_funding__without_external_funding__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()

    builder = ArticleRequestDataBuilder().without_external_funding()

    wizard = update_funding_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    request = repository.get_by_id(fr_id)
    assert list(request.external_funding) == []
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))
