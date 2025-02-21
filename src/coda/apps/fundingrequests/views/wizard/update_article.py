from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.steps.extrainformation_step import (
    ExtraInformationStep,
)
from coda.apps.fundingrequests.views.wizard.steps.funding_step import FundingStep
from coda.apps.fundingrequests.views.wizard.steps.journal_step import JournalStep
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.repositories import publication_repository
from coda.apps.wizard import SessionStore, Wizard


class UpdateExtraInformationView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [ExtraInformationStep()]

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        contact = ExtraContactDto(**store.get("contact", {}))
        extra_info = ExtraInformationDto(
            request_remarks=store.get("request_remarks"), extra_contact=contact
        )

        services.update_extra_information(self.kwargs["pk"], extra_info)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        store["request_remarks"] = fr.request_remarks
        if fr.extra_contact:
            store["contact"] = {"name": fr.extra_contact.name, "email": fr.extra_contact.email}
            store.save()


class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep.for_article(), JournalStep()]
    allow_early_complete = True

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        pk = kwargs["pk"]
        fr = fundingrequest_repository.get_article_request(pk)
        dto = publication_dto_from(self.get_store())
        publication = dto.to_publication(fr.publication.id)
        publication_repository.save(publication)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_article_request(self.kwargs["pk"])
        dto = PublicationDto.from_publication(fr.publication)
        store["publication_step"] = dto.to_post_data(exclude={"journal", "contracts"})
        store["journal"] = fr.publication.journal
        store["contracts"] = [c.to_post_data() for c in dto.contracts]
        store.save()


class UpdateFundingView(LoginRequiredMixin, Wizard):
    steps = [FundingStep()]
    store_name = "update_funding_wizard"
    store_factory = SessionStore

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        cost = PaymentDto(**store["cost"])
        funding = []
        if store.get("funding") is not None:
            funding = [ExternalFundingDto(**f) for f in store["funding"]]
        services.update_funding(self.kwargs["pk"], cost, funding)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = fundingrequest_repository.get_by_id(self.kwargs["pk"])
        store["cost"] = PaymentDto.from_payment(fr.estimated_cost).to_post_data()

        store["funding"] = [
            ExternalFundingDto.from_external_funding(external_funding).to_post_data()
            for external_funding in fr.external_funding
        ]
        store.save()
