import functools
from collections.abc import Callable

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import MonographDto
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.fundingrequests.wizard.stepdata import publication_step
from tests.fundingrequests.wizard.test_fundingrequest_article_wizard import (
    submit_complete_early,
    submit_step,
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
@pytest.mark.usefixtures("logged_in")
def test__updating_monograph_meta_step__saves_fundingrequest_with_changed_data(
    client: Client,
) -> None:
    builder = MonographRequestDataBuilder()
    id = repository.save(builder.build())
    url = reverse("fundingrequests:update_monograph_meta", kwargs={"pk": id})
    submit = functools.partial(submit_step, client, url)

    monograph = repository.get_monograph_request(id)
    updated = builder.with_new_publication(monograph.publication.id)

    response = submit(publication_step.stepdata(updated.publication_dto()))
    response = submit(updated.publisher_step_dto().page_input())

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
    url = reverse("fundingrequests:update_monograph_meta", kwargs={"pk": id})
    submit = functools.partial(submit_complete_early, client, url)

    monograph = repository.get_monograph_request(id)
    updated = (
        builder.with_new_publication(id=monograph.publication.id)
        .with_contracts(monograph.publication.contracts)
        .with_publisher(monograph.publication.publisher)
    )

    _ = client.get(url)
    response = submit(publication_step.stepdata(updated.publication_dto()))

    actual = repository.get_monograph_request(id)
    assert_fundingrequest_eq(actual, updated.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": id}))


def submit_wizard(
    client: Client,
    extra_contact: ExtraContactDto,
    monograph: MonographDto,
    external_funding: list[ExternalFundingDto],
    cost: PaymentDto,
) -> HttpResponse:
    url = reverse("fundingrequests:create_monograph")
    submit = functools.partial(submit_step, client, url)

    fundings = to_htmx_formset_data(external_funding)

    submit(
        PublisherStepDto(publisher=monograph.publisher, contracts=monograph.contracts).page_input()
    )
    submit(publication_step.stepdata(monograph))
    submit(fundings | cost.to_post_data())
    return submit(extra_contact.to_post_data())
