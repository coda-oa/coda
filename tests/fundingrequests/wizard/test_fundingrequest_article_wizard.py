import functools
from collections.abc import Callable
from typing import Any, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import PublicationDto
from coda.apps.users.models import User
from coda.fundingrequest import (
    FilledContact,
    FundingRequestContact,
    FundingRequestId,
    NoContact,
)
from coda.publication import JournalId
from coda.string import NonEmptyStr
from coda.vocabulary import VocabularyConcept
from tests import domainfactory
from tests.fundingrequests.test_fundingrequest_services import (
    assert_fundingrequest_contact_eq,
    assert_fundingrequest_eq,
)
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.stepdata import publication_step
from tests.publications.test_publication_repository import assert_publication_eq
from tests.test_wizard import complete_early, next


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
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client, get_builder: BuilderFactory
) -> None:
    builder = get_builder()

    response = submit_wizard(
        client,
        builder.extra_contact_dto(),
        builder.publication_dto(),
        builder.external_funding_dto(),
        builder.cost_dto(),
    )

    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, builder.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "expected",
    [
        NoContact,
        FilledContact(name=NonEmptyStr("John Doe"), email="j.doe@example.com"),
    ],
    ids=["empty_contact", "filled_contact"],
)
def test__updating_fundingrequest_contact__updates_funding_request_and_shows_details(
    client: Client, expected: FundingRequestContact
) -> None:
    fr_id = save_new_fundingrequest()
    wizard_url = reverse("fundingrequests:update_submitter", kwargs={"pk": fr_id})

    new_contact = ExtraContactDto.from_contact(expected)
    response = submit_step(client, wizard_url, new_contact.to_post_data())

    actual = repository.get_by_id(fr_id).extra_contact
    assert_fundingrequest_contact_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_publication__updates_fundingrequest_and_shows_details(
    client: Client,
) -> None:
    existing_request_id = save_new_fundingrequest()

    builder = ArticleRequestDataBuilder()
    response = submit_update_publication_wizard(
        client,
        existing_request_id,
        JournalId(builder.journal.id),
        builder.publication_dto(),
    )

    expected = builder.expected.publication
    actual = repository.get_by_id(existing_request_id).publication
    assert_publication_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": existing_request_id}))


@pytest.mark.django_db
def test__updating_publication_page_of_update_publication_wizard__saves_early(
    client: Client,
) -> None:
    existing_request_id = save_new_fundingrequest()
    existing_request = repository.get_article_request(existing_request_id)

    builder = (
        ArticleRequestDataBuilder()
        .with_contracts(existing_request.publication.contracts)
        .with_journal(existing_request.publication.journal)
    )

    wizard_url = reverse("fundingrequests:update_publication", kwargs={"pk": existing_request_id})
    submit = functools.partial(submit_complete_early, client, wizard_url)

    publication_formdata = publication_step.stepdata(builder.publication_dto())

    _ = client.get(wizard_url)
    submit(publication_formdata)

    actual = repository.get_by_id(existing_request_id).publication
    assert_publication_eq(actual, builder.expected.publication)


@pytest.mark.django_db
def test__updating_fundingrequest_funding__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()
    fr_before_update = repository.get_by_id(fr_id)

    builder = ArticleRequestDataBuilder().with_payment(fr_before_update.estimated_cost)
    external_funding = builder.external_funding_dto()
    external_funding_data = [ef.to_post_data() for ef in external_funding]
    cost_dto = builder.cost_dto()

    data = to_htmx_formset_data(external_funding_data) | cost_dto.to_post_data()
    response = submit_update_funding_wizard(client, fr_id, data)

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
    cost_dto = PaymentDto.from_payment(domainfactory.payment())
    empty_funding_data = to_htmx_formset_data(
        [
            {
                "organization": "",
                "project_id": "",
                "project_name": "",
            }
        ]
    )

    data = empty_funding_data | cost_dto.to_post_data()
    response = submit_update_funding_wizard(client, fr_id, data)

    request = repository.get_by_id(fr_id)
    assert list(request.external_funding) == []
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


def submit_wizard(
    client: Client,
    extra_contact: ExtraContactDto,
    publication: PublicationDto,
    external_funding: list[ExternalFundingDto],
    cost: PaymentDto,
) -> HttpResponse:
    create_wizard_url = reverse("fundingrequests:create_wizard")
    submit = functools.partial(submit_step, client, create_wizard_url)

    fundings = to_htmx_formset_data(external_funding)
    contracts = to_htmx_formset_data(
        [{"contract": c.contract, "year": c.year} for c in publication.contracts],
        prefix="contracts",
    )
    journal = {"journal": publication.journal.id}
    submit(journal | contracts)
    submit(publication_step.stepdata(publication))
    submit(fundings | cost.to_post_data())
    return submit(extra_contact.to_post_data())


def submit_update_publication_wizard(
    client: Client, fr_id: FundingRequestId, journal_id: JournalId, publication_dto: PublicationDto
) -> HttpResponse:
    wizard_url = reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
    submit = functools.partial(submit_step, client, wizard_url)

    publication_formdata = publication_step.stepdata(publication_dto)
    submit(publication_formdata)

    journal_post_data = {"journal": journal_id}
    contracts = to_htmx_formset_data(
        [{"contract": c.contract, "year": c.year} for c in publication_dto.contracts],
        prefix="contracts",
    )
    journal_stepdata = journal_post_data | contracts
    return submit(journal_stepdata)


def submit_update_funding_wizard(
    client: Client, fr_id: FundingRequestId, data: dict[str, Any]
) -> HttpResponse:
    wizard_url = reverse("fundingrequests:update_funding", kwargs={"pk": fr_id})
    return submit_step(client, wizard_url, data)


def submit_step(client: Client, url: str, form_data: dict[str, Any]) -> HttpResponse:
    return cast(HttpResponse, client.post(url, next() | form_data))


def submit_complete_early(client: Client, url: str, form_data: dict[str, Any]) -> HttpResponse:
    return cast(HttpResponse, client.post(url, complete_early() | form_data))


def subject_area() -> VocabularyConcept:
    return list(GlobalPreferences.get_subject_classification_vocabulary().concepts)[0]


def publication_type() -> VocabularyConcept:
    return list(GlobalPreferences.get_article_publication_type_vocabulary().concepts)[0]
