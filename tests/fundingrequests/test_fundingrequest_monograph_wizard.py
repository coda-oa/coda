import functools

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import MonographDto
from coda.contract import ContractId, PublisherId
from coda.publication import Monograph
from tests import domainfactory, modelfactory
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.test_fundingrequest_wizard import FundingRequestDataBuilder, submit_step
from tests.fundingrequests.wizard.stepdata import publication_step


class MonographRequestDataBuilder(FundingRequestDataBuilder):
    def __init__(self) -> None:
        super().__init__()
        publisher = modelfactory.publisher()
        self._publication = domainfactory.monograph(
            publisher=PublisherId(publisher.pk),
            publication_type=list(self.publication_types.concepts)[0],
            subject_area=list(self.subject_areas.concepts)[0],
            contracts=tuple(ContractId(c.pk) for c in self.contracts),
        )

    @property
    def publication(self) -> Monograph:
        return self._publication

    def publication_dto(self) -> MonographDto:
        return MonographDto.from_monograph(self.publication)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__completing_monograph_wizard__creates_funding_request_for_monograph_and_shows_details(
    client: Client,
) -> None:
    builder = MonographRequestDataBuilder()

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


def submit_wizard(
    client: Client,
    author: AuthorDto,
    monograph: MonographDto,
    external_funding: list[ExternalFundingDto],
    cost: PaymentDto,
) -> HttpResponse:
    url = reverse("fundingrequests:create_monograph")
    submit = functools.partial(submit_step, client, url)

    fundings = to_htmx_formset_data(external_funding)

    submit(author.to_post_data())
    submit(
        PublisherStepDto(publisher=monograph.publisher, contracts=monograph.contracts).page_input()
    )
    submit(publication_step.stepdata(monograph))
    return submit(fundings | cost.to_post_data())
