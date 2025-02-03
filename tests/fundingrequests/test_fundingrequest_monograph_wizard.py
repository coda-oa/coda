from collections.abc import Callable
import functools
from typing import Self

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import MonographDto
from coda.contract import PublisherId
from coda.publication import Monograph, PublicationId
from tests import domainfactory, modelfactory
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.test_fundingrequest_wizard import FundingRequestDataBuilder, submit_step
from tests.fundingrequests.wizard.stepdata import publication_step


class MonographRequestDataBuilder(FundingRequestDataBuilder[Monograph]):
    def __init__(self) -> None:
        super().__init__()
        publisher = modelfactory.publisher()
        self._publication = self.create_monograph(PublisherId(publisher.pk))

    def create_monograph(
        self, publisher: PublisherId, id: PublicationId | None = None
    ) -> Monograph:
        return domainfactory.monograph(
            publisher=publisher,
            publication_type=list(self.publication_types.concepts)[0],
            subject_area=list(self.subject_areas.concepts)[0],
            contracts=tuple(self.contract_years),
            id=id,
        )

    def with_new_publication(self, id: PublicationId | None = None) -> Self:
        publisher = modelfactory.publisher()
        self._publication = self.create_monograph(PublisherId(publisher.pk), id)
        return self

    @property
    def publication(self) -> Monograph:
        return self._publication

    def publication_dto(self) -> MonographDto:
        return MonographDto.from_monograph(self.publication)

    def publisher_step_dto(self) -> PublisherStepDto:
        return PublisherStepDto.from_monograph(self.publication)


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
        builder.submitter_dto(),
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
    id = fundingrequest_create(builder.build())
    url = reverse("fundingrequests:update_monograph_meta", kwargs={"pk": id})
    submit = functools.partial(submit_step, client, url)

    monograph = repository.get_monograph_request(id)
    updated = builder.with_new_publication(monograph.publication.id)

    _ = submit(updated.publisher_step_dto().page_input())
    response = submit(publication_step.stepdata(updated.publication_dto()))

    actual = repository.get_monograph_request(id)
    assert_fundingrequest_eq(actual, updated.expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


def submit_wizard(
    client: Client,
    extra_contact: dict[str, str],
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
    return submit(extra_contact)
