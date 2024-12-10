import abc
import functools
from typing import Any, Self, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.users.models import User
from coda.author import InstitutionId
from coda.contract import ContractId
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
)
from coda.publication import BasePublication, JournalId, Publication
from coda.vocabulary import VocabularyConcept
from tests import domainfactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.fundingrequests.wizard.stepdata import publication_step
from tests.publications.test_publication_services import assert_publication_eq


class FundingRequestDataBuilder:
    def __init__(self) -> None:
        self.affiliation = modelfactory.institution()
        self.funder = modelfactory.funding_organization()
        self.contracts = [modelfactory.contract() for _ in range(1, 3)]

        self.submitter = domainfactory.author(affiliation=InstitutionId(self.affiliation.pk))
        self.estimated_cost = domainfactory.payment()
        self.external_funding = [
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
        ]

        self.prepare_vocabularies()
        self.set_global_preferences()

    def prepare_vocabularies(self) -> None:
        self.subject_areas = vocabulary_repository.create("subject_areas", "1.0")
        self.subject_areas.add_concept("subject_area", "subject_area")
        vocabulary_repository.save(self.subject_areas)

        self.publication_types = vocabulary_repository.create("publication_types", "1.0")
        self.publication_types.add_concept("publication_type", "publication_type")
        vocabulary_repository.save(self.publication_types)

    def set_global_preferences(self) -> None:
        GlobalPreferences.set_subject_classification_vocabulary(self.subject_areas)
        GlobalPreferences.set_publication_type_vocabulary(self.publication_types)

    @property
    @abc.abstractmethod
    def publication(self) -> BasePublication:
        ...

    def build(self) -> FundingRequest:
        return FundingRequest.new(
            self.publication,
            self.submitter,
            self.estimated_cost,
            self.external_funding,
        )

    @property
    def expected(self) -> FundingRequest:
        return self.build()

    def with_payment(self, payment: Payment) -> Self:
        self.estimated_cost = payment
        return self

    def submitter_dto(self) -> AuthorDto:
        return AuthorDto.from_author(self.submitter)

    def external_funding_dto(self) -> list[ExternalFundingDto]:
        return [self._to_external_funding_dto(f) for f in self.external_funding]

    def cost_dto(self) -> PaymentDto:
        return PaymentDto.from_payment(self.estimated_cost)

    def _to_external_funding_dto(self, funding: ExternalFunding) -> ExternalFundingDto:
        return ExternalFundingDto.from_external_funding(funding)


class ArticleRequestDataBuilder(FundingRequestDataBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.journal = modelfactory.journal()
        self._publication = domainfactory.publication(
            journal=JournalId(self.journal.pk),
            publication_type=list(self.publication_types.concepts)[0],
            subject_area=list(self.subject_areas.concepts)[0],
            contracts=tuple(ContractId(c.pk) for c in self.contracts),
        )

    @property
    def publication(self) -> Publication:
        return self._publication

    def publication_dto(self) -> PublicationDto:
        return PublicationDto.from_publication(self._publication)


@pytest.fixture(autouse=True)
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


def save_new_fundingrequest() -> FundingRequestId:
    fr = ArticleRequestDataBuilder().expected
    fr_id = fundingrequest_create(fr)
    return fr_id


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    builder = ArticleRequestDataBuilder()

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
def test__updating_fundingrequest_submitter__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    fr_id = save_new_fundingrequest()
    wizard_url = reverse("fundingrequests:update_submitter", kwargs={"pk": fr_id})

    affiliation = modelfactory.institution()
    new_author = domainfactory.author(InstitutionId(affiliation.pk))
    new_author_dto = AuthorDto.from_author(new_author)
    response = submit_step(client, wizard_url, new_author_dto.to_post_data())

    expected = new_author
    actual = repository.get_by_id(fr_id).submitter
    assert_author_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_publication__updates_funding_request_and_shows_details(
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


def next() -> dict[str, str]:
    return {"action": "next"}


def submit_wizard(
    client: Client,
    author: AuthorDto,
    publication: PublicationDto,
    external_funding: list[ExternalFundingDto],
    cost: PaymentDto,
) -> HttpResponse:
    create_wizard_url = reverse("fundingrequests:create_wizard")
    submit = functools.partial(submit_step, client, create_wizard_url)

    fundings = to_htmx_formset_data(external_funding)
    contracts = to_htmx_formset_data([{"contract": cid} for cid in publication.contracts])
    journal = {"journal": publication.journal.id}
    submit(author.to_post_data())
    submit(journal | contracts)
    submit(publication_step.stepdata(publication))
    return submit(fundings | cost.to_post_data())


def submit_update_publication_wizard(
    client: Client, fr_id: FundingRequestId, journal_id: JournalId, publication_dto: PublicationDto
) -> HttpResponse:
    wizard_url = reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
    submit = functools.partial(submit_step, client, wizard_url)

    publication_formdata = publication_step.stepdata(publication_dto)
    submit(publication_formdata)

    journal_post_data = {"journal": journal_id}
    contracts = to_htmx_formset_data([{"contract": cid} for cid in publication_dto.contracts])
    return submit(journal_post_data | contracts)


def submit_update_funding_wizard(
    client: Client, fr_id: FundingRequestId, data: dict[str, Any]
) -> HttpResponse:
    wizard_url = reverse("fundingrequests:update_funding", kwargs={"pk": fr_id})
    return submit_step(client, wizard_url, data)


def submit_step(client: Client, url: str, form_data: dict[str, Any]) -> HttpResponse:
    return cast(HttpResponse, client.post(url, next() | form_data))


def subject_area() -> VocabularyConcept:
    return list(GlobalPreferences.get_subject_classification_vocabulary().concepts)[0]


def publication_type() -> VocabularyConcept:
    return list(GlobalPreferences.get_publication_type_vocabulary().concepts)[0]
