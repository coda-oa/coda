import abc
from typing import Generic, TypeVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import ExternalFundingDto, ExtraContactDto, PaymentDto
from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.apps.wizard import Store, Wizard
from coda.fundingrequests.identity import PublicFundingRequestId

TPublicationDto = TypeVar("TPublicationDto", PublicationDto, MonographDto)


class FundingRequestCreationWizard(LoginRequiredMixin, Wizard, abc.ABC, Generic[TPublicationDto]):
    cancel_url = reverse_lazy("fundingrequests:list")
    request_id_generator = PublicFundingRequestId.create

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: dict[str, str]) -> None:
        store = self.get_store()
        publication = self.parse_publication(store)
        cost = PaymentDto(**store["cost"])
        funding = self.parse_funding(store)
        extra_contact = self.parse_contact(store)
        funding_request_id = services.create_fundingrequest(
            publication,
            cost,
            funding,
            extra_contact,
        )
        store["funding_request"] = funding_request_id
        store.save()

    def parse_funding(self, store: Store) -> list[ExternalFundingDto]:
        return [ExternalFundingDto(**f) for f in store.get("funding", [])]

    def parse_contact(self, store: Store) -> ExtraContactDto:
        return ExtraContactDto(**store.get("contact", {}))

    @abc.abstractmethod
    def parse_publication(self, store: Store) -> TPublicationDto:
        ...
