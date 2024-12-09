import functools

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

# from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import MonographDto

# from coda.publication import Monograph
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.test_fundingrequest_wizard import FundingRequestDataBuilder, submit_step


class MonographRequestDataBuilder(FundingRequestDataBuilder):
    def __init__(self) -> None:
        super().__init__()
        # self.publication = Monograph()

    # def publication_dto(self) -> MonographDto:
    #     return None


@pytest.mark.django_db
def test__completing_monograph_wizard__creates_funding_request_for_monograph_and_shows_details(
    client: Client,
) -> None:
    builder = FundingRequestDataBuilder()

    # response = submit_wizard(
    #     client,
    #     builder.submitter_dto(),
    #     builder.publication_dto(),
    #     builder.external_funding_dto(),
    #     builder.cost_dto(),
    # )

    actual = repository.first()
    assert actual is not None
    assert_fundingrequest_eq(actual, builder.expected)
    # assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": actual.id}))


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
    contracts = to_htmx_formset_data([{"contract": cid} for cid in monograph.contracts])
    journal = {"publisher": monograph.publisher}
    submit(author.to_post_data())
    submit(journal | contracts)
    # submit(publication_step.stepdata(publication))
    return submit(fundings | cost.to_post_data())
