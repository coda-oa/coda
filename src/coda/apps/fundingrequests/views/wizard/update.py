from coda.apps.authors.dto import author_dto_from_model, parse_author
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_update
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import (
    CostDto,
    ExternalFundingDto,
    parse_external_funding,
    parse_payment,
)
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.publications.dto import parse_publication, publication_dto_from_model
from coda.apps.publications.services import publication_update
from coda.apps.wizard import SessionStore, Wizard
from coda.author import AuthorId


from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse


from typing import Any, cast

from coda.publication import PublicationId


class UpdateSubmitterView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequestModel, pk=self.kwargs["pk"])
        submitter_id = AuthorId(cast(AuthorModel, fr.submitter).pk)
        author = parse_author(store["submitter"], submitter_id)
        author_update(author)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequestModel, pk=self.kwargs["pk"])
        if fr.submitter:
            store["submitter"] = author_dto_from_model(fr.submitter) | {"id": fr.submitter.pk}
            store.save()


class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep(), JournalStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        pk = kwargs["pk"]
        funding_request = get_object_or_404(FundingRequestModel, pk=pk)
        publication_update(
            parse_publication(
                publication_dto_from(self.get_store()),
                PublicationId(funding_request.publication.pk),
            )
        )

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequestModel, pk=self.kwargs["pk"])
        dto = publication_dto_from_model(fr.publication)
        store["publication"] = dto
        store["authors"] = list(dto["authors"])
        store["journal"] = fr.publication.journal.pk
        store["links"] = dto["links"]
        store.save()


class UpdateFundingView(LoginRequiredMixin, Wizard):
    steps = [FundingStep()]
    store_name = "update_funding_wizard"
    store_factory = SessionStore

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        cost = parse_payment(store["cost"])
        funding = parse_external_funding(store["funding"]) if store.get("funding") else None
        services.fundingrequest_funding_update(self.kwargs["pk"], cost, funding)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequestModel, pk=self.kwargs["pk"])
        store["cost"] = CostDto(
            estimated_cost=float(fr.estimated_cost),
            estimated_cost_currency=fr.estimated_cost_currency,
            payment_method=fr.payment_method,
        )
        if fr.external_funding:
            store["funding"] = ExternalFundingDto(
                organization=fr.external_funding.organization.pk,
                project_id=fr.external_funding.project_id,
                project_name=fr.external_funding.project_name,
            )
        store.save()
