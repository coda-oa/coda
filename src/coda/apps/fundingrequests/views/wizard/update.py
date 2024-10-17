from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.authors.dto import parse_author, to_author_dto
from coda.apps.authors.services import author_update
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import (
    CostDto,
    ExternalFundingDto,
    parse_external_funding,
    parse_payment,
)
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.publications.dto import parse_publication, to_publication_dto
from coda.apps.publications.services import publication_update
from coda.apps.wizard import SessionStore, Wizard


class UpdateSubmitterView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        author = parse_author(store["submitter"], fr.submitter.id)
        author_update(author)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        store["submitter"] = to_author_dto(fr.submitter) | {"id": fr.submitter.id}
        store.save()


class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep(), JournalStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        pk = kwargs["pk"]
        fr = fundingrequest_repository.get_by_id(pk)
        publication_update(
            parse_publication(publication_dto_from(self.get_store()), fr.publication.id)
        )

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        dto = to_publication_dto(fr.publication)
        store["publication"] = dto["meta"]
        store["authors"] = list(dto["authors"])
        store["journal"] = fr.publication.journal
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
        funding = [parse_external_funding(store["funding"])] if store.get("funding") else []
        services.fundingrequest_funding_update(self.kwargs["pk"], cost, funding)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        store["cost"] = CostDto(
            estimated_cost=float(fr.estimated_cost.amount.amount),
            estimated_cost_currency=fr.estimated_cost.amount.currency.code,
            payment_method=fr.estimated_cost.method.value,
        )
        if fr.external_funding:
            external_funding = next(iter(fr.external_funding))
            store["funding"] = ExternalFundingDto(
                organization=external_funding.organization,
                project_id=external_funding.project_id,
                project_name=external_funding.project_name,
            )
        store.save()
