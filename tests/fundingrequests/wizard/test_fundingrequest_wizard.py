from collections.abc import Callable

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.users.models import User
from coda.domain.fundingrequest import FundingRequestId
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.fundingrequests.wizard.wizardsubmitter import (
    TDataBuilder,
    article_wizardsubmitter,
    complete_early_iterator,
    monograph_wizardsubmitter,
    update_article_publication_wizard,
    update_extra_information_wizard,
    update_funding_wizard,
    update_monograph_publication_wizard,
)
from tests.fundingrequests.wizard.wizardsubmitter.decorator import (
    BuilderFactory,
    CreationWizardSubmitterFactory,
    UpdateWizardSubmitterFactory,
    UseWizardSubmitter,
)
from tests.publications.test_publication_repository import assert_publication_eq


@pytest.fixture(autouse=True)
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


@pytest.mark.django_db
@UseWizardSubmitter.distinct(
    article_wizardsubmitter,
    monograph_wizardsubmitter,
    article_builders=[
        ArticleRequestDataBuilder,
        lambda: ArticleRequestDataBuilder().with_empty_contact(),
    ],
    monograph_builders=[
        MonographRequestDataBuilder,
        lambda: MonographRequestDataBuilder().with_empty_contact(),
    ],
)
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: CreationWizardSubmitterFactory[TDataBuilder],
) -> None:
    builder = get_builder()
    wizard = get_wizard(client, builder)

    response = wizard.submit_all()

    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, builder.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
@UseWizardSubmitter.singular(update_extra_information_wizard)
def test__updating_fundingrequest_extra_information__updates_funding_request_and_shows_details(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: UpdateWizardSubmitterFactory[TDataBuilder],
) -> None:
    builder = get_builder()
    fr_id = repository.create(builder.expected)

    builder = builder.with_new_contact().with_new_request_remarks()
    wizard = get_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    expected = builder.expected
    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
@UseWizardSubmitter.distinct(update_article_publication_wizard, update_monograph_publication_wizard)
def test__updating_fundingrequest_publication__updates_fundingrequest_and_shows_details(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: UpdateWizardSubmitterFactory[TDataBuilder],
) -> None:
    builder = get_builder()
    id = repository.create(builder.build())

    saved = repository.get_by_id(id)
    updated = builder.with_new_publication(saved.publication.id)

    wizard = get_wizard(client, id, updated)
    response = wizard.submit_all()

    actual = repository.get_by_id(id)
    assert_fundingrequest_eq(actual, updated.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": id}))


def update_article_meta(
    builder: ArticleRequestDataBuilder, id: FundingRequestId
) -> ArticleRequestDataBuilder:
    article = repository.get_article_request(id).publication

    return (
        builder.with_new_publication(article.id)
        .with_contracts(article.contracts)
        .with_journal(article.journal)
    )


def update_monograph_meta(
    builder: MonographRequestDataBuilder, id: FundingRequestId
) -> MonographRequestDataBuilder:
    monograph = repository.get_monograph_request(id).publication

    return (
        builder.with_new_publication(monograph.id)
        .with_contracts(monograph.contracts)
        .with_publisher(monograph.publisher)
    )


@pytest.mark.django_db
@UseWizardSubmitter.distinct(
    update_article_publication_wizard,
    update_monograph_publication_wizard,
    article_args={"update_meta": update_article_meta},
    monograph_args={"update_meta": update_monograph_meta},
)
def test__updating_only_publication_page_of_update_publication_wizard__saves_early(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: UpdateWizardSubmitterFactory[TDataBuilder],
    update_meta: Callable[[TDataBuilder, FundingRequestId], TDataBuilder],
) -> None:
    builder = get_builder()
    existing_request_id = repository.create(builder.build())

    builder = update_meta(builder, existing_request_id)

    wizard = get_wizard(client, existing_request_id, builder)
    wizard.step_iterator = complete_early_iterator(until=0)

    wizard.submit_all()

    actual = repository.get_by_id(existing_request_id).publication
    assert_publication_eq(actual, builder.expected.publication)


@pytest.mark.django_db
@UseWizardSubmitter.singular(update_funding_wizard)
def test__updating_fundingrequest_funding__updates_funding_request_and_shows_details(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: UpdateWizardSubmitterFactory[TDataBuilder],
) -> None:
    builder = get_builder()
    fr_id = repository.create(builder.build())
    fr_before_update = repository.get_by_id(fr_id)

    builder = builder.with_payment(fr_before_update.estimated_cost)

    wizard = get_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    fr = repository.get_by_id(fr_id)
    expected_payment = builder.expected.estimated_cost
    expected_funding = builder.expected.external_funding
    assert fr.estimated_cost == expected_payment
    assert list(fr.external_funding) == list(expected_funding)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
@UseWizardSubmitter.singular(update_funding_wizard)
def test__updating_fundingrequest_funding__without_external_funding__updates_funding_request_and_shows_details(
    client: Client,
    get_builder: BuilderFactory[TDataBuilder],
    get_wizard: UpdateWizardSubmitterFactory[TDataBuilder],
) -> None:
    builder = get_builder()
    fr_id = repository.create(builder.build())

    builder = builder.without_external_funding()

    wizard = get_wizard(client, fr_id, builder)
    response = wizard.submit_all()

    request = repository.get_by_id(fr_id)
    assert list(request.external_funding) == []
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))
