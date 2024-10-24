import json
from typing import Any, cast

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from coda.apps.authors.dto import AuthorDto, parse_author, to_author_dto
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.services import fundingrequest_create
from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import PublicationDto, PublicationMetaDto, to_publication_dto
from coda.apps.users.models import User
from coda.author import InstitutionId
from coda.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Payment,
)
from coda.contract import ContractId
from coda.publication import JournalId, VocabularyConcept
from tests import domainfactory, dtofactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.test_fundingrequest_services import assert_fundingrequest_eq
from tests.publications.test_publication_services import as_domain_concept, assert_publication_eq


class FundingRequestDataBuilder:
    def __init__(self) -> None:
        self.affiliation = modelfactory.institution()
        self.journal = modelfactory.journal()
        self.funder = modelfactory.funding_organization()
        self.contracts = [modelfactory.contract() for _ in range(1, 3)]

        self.submitter = domainfactory.author(affiliation=InstitutionId(self.affiliation.pk))
        self.publication = domainfactory.publication(
            journal=JournalId(self.journal.pk),
            publication_type=publication_type(),
            subject_area=subject_area(),
            contracts=tuple(ContractId(c.pk) for c in self.contracts),
        )
        self.estimated_cost = domainfactory.payment()
        self.external_funding = [
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
        ]

    def with_payment(self, payment: Payment) -> "FundingRequestDataBuilder":
        self.estimated_cost = payment
        return self

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

    def submitter_dto(self) -> AuthorDto:
        return to_author_dto(self.submitter)

    def publication_dto(self) -> PublicationDto:
        return to_publication_dto(self.publication)

    def external_funding_dto(self) -> list[ExternalFundingDto]:
        return [self._to_external_funding_dto(f) for f in self.external_funding]

    def cost_dto(self) -> CostDto:
        return CostDto(
            estimated_cost=float(self.estimated_cost.amount.amount),
            estimated_cost_currency=self.estimated_cost.amount.currency.code,
            payment_method=self.estimated_cost.method.value,
        )

    def _to_external_funding_dto(self, funding: ExternalFunding) -> ExternalFundingDto:
        return ExternalFundingDto(
            organization=funding.organization,
            project_id=funding.project_id,
            project_name=funding.project_name,
        )


@pytest.fixture(autouse=True)
def login(client: Client) -> None:
    client.force_login(User.objects.create_user(username="testuser"))


@pytest.fixture(autouse=True)
def prepare_global_settings() -> None:
    GlobalPreferences.set_subject_classification_vocabulary(modelfactory.vocabulary())
    GlobalPreferences.set_publication_type_vocabulary(modelfactory.vocabulary())


def save_new_fundingrequest() -> FundingRequestId:
    fr = FundingRequestDataBuilder().expected
    fr_id = fundingrequest_create(fr)
    return fr_id


@pytest.mark.django_db
def test__completing_fundingrequest_wizard__creates_funding_request_and_shows_details(
    client: Client,
) -> None:
    builder = FundingRequestDataBuilder()

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
    affiliation = modelfactory.institution()

    new_author = dtofactory.author_dto(affiliation.pk)
    response = client.post(
        reverse("fundingrequests:update_submitter", kwargs={"pk": fr_id}),
        next() | new_author,
    )

    expected = parse_author(new_author)
    actual = repository.get_by_id(fr_id).submitter
    assert_author_eq(actual, expected)
    assertRedirects(response, reverse("fundingrequests:detail", kwargs={"pk": fr_id}))


@pytest.mark.django_db
def test__updating_fundingrequest_publication__updates_funding_request_and_shows_details(
    client: Client,
) -> None:
    existing_request_id = save_new_fundingrequest()

    builder = FundingRequestDataBuilder()
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

    builder = FundingRequestDataBuilder().with_payment(fr_before_update.estimated_cost)
    external_funding = builder.external_funding_dto()
    cost_dto = builder.cost_dto()

    response = client.post(
        reverse("fundingrequests:update_funding", kwargs={"pk": fr_id}),
        next() | to_htmx_formset_data(external_funding) | cost_dto,
    )

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
    cost_dto = dtofactory.cost_dto()
    empty_funding_data = to_htmx_formset_data(
        [
            {
                "organization": "",
                "project_id": "",
                "project_name": "",
            }
        ]
    )

    response = client.post(
        reverse("fundingrequests:update_funding", kwargs={"pk": fr_id}),
        next() | empty_funding_data | cost_dto,
    )

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
    cost: CostDto,
) -> HttpResponse:
    create_wizard_url = reverse("fundingrequests:create_wizard")
    fundings = to_htmx_formset_data(external_funding)
    contracts = to_htmx_formset_data([{"contract": cid} for cid in publication["contracts"]])
    client.post(create_wizard_url, next() | author)
    client.post(
        create_wizard_url,
        next() | {"journal": publication["journal"]["journal_id"]} | contracts,
    )
    client.post(create_wizard_url, next() | as_form_data(publication))
    return cast(
        HttpResponse,
        client.post(create_wizard_url, next() | fundings | cost),
    )


def submit_update_publication_wizard(
    client: Client, fr_id: FundingRequestId, journal_id: JournalId, publication_dto: PublicationDto
) -> HttpResponse:
    wizard_url = reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})

    publication_formdata = as_form_data(publication_dto)
    client.post(wizard_url, next() | publication_formdata)

    journal_post_data = {"journal": journal_id}
    contracts = to_htmx_formset_data([{"contract": cid} for cid in publication_dto["contracts"]])
    response = client.post(wizard_url, next() | journal_post_data | contracts)

    return cast(HttpResponse, response)


def subject_area() -> VocabularyConcept:
    concept_model = GlobalPreferences.get_subject_classification_vocabulary().concepts.first()
    assert concept_model is not None
    return as_domain_concept(concept_model)


def publication_type() -> VocabularyConcept:
    concept_model = GlobalPreferences.get_publication_type_vocabulary().concepts.first()
    assert concept_model is not None
    return as_domain_concept(concept_model)


def as_form_data(publication: PublicationDto) -> dict[str, Any]:
    meta = publication["meta"]
    meta["online_publication_date"] = meta["online_publication_date"] or ""
    meta["print_publication_date"] = meta["print_publication_date"] or ""

    # NOTE: authors are submitted as a single string from a textarea
    authors = ",".join(publication["authors"])

    concepts = _concepts_to_json(meta)

    meta_reduced = dict(meta)
    meta_reduced.pop("subject_area")
    meta_reduced.pop("publication_type")
    meta_reduced.pop("subject_area_vocabulary")
    meta_reduced.pop("publication_type_vocabulary")

    link_form_data: dict[str, list[str]] = {"link_type": [], "link_value": []}
    for link in publication["links"]:
        link_form_data["link_type"].append(str(link["link_type"]))
        link_form_data["link_value"].append(str(link["link_value"]))

    formdata = meta_reduced | {"authors": authors} | concepts | link_form_data
    return formdata


def _concepts_to_json(meta: PublicationMetaDto) -> dict[str, str]:
    return {
        "subject_area": json.dumps(
            {
                "concept": meta["subject_area"],
                "vocabulary": meta["subject_area_vocabulary"],
            }
        ),
        "publication_type": json.dumps(
            {
                "concept": meta["publication_type"],
                "vocabulary": meta["publication_type_vocabulary"],
            }
        ),
    }
