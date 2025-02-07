import abc
from typing import Generic, TypeVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.wizard import Store, Wizard
from coda.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingRequest,
    FundingRequestContact,
    NoContact,
)
from coda.publication import Monograph, Publication

TPublication = TypeVar("TPublication", Publication, Monograph)


class FundingRequestCreationWizard(LoginRequiredMixin, Wizard, abc.ABC, Generic[TPublication]):
    cancel_url = reverse_lazy("fundingrequests:list")

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: dict[str, str]) -> None:
        store = self.get_store()
        publication = self.parse_publication(store)
        cost = PaymentDto(**store["cost"]).to_payment()
        funding = self.parse_funding(store)
        extra_contact = self.parse_contact(store)
        funding_request_id = services.fundingrequest_create(
            FundingRequest.new(publication, cost, funding, extra_contact)
        )
        store["funding_request"] = funding_request_id
        store.save()

    def parse_funding(self, store: Store) -> list[ExternalFunding]:
        return [ExternalFundingDto(**f).to_external_funding() for f in store.get("funding", [])]

    def parse_contact(self, store: Store) -> FundingRequestContact:
        return (
            FilledContact(store["contact"]["name"], store["contact"]["email"])
            if "contact" in store
            else NoContact
        )

    @abc.abstractmethod
    def parse_publication(self, store: Store) -> TPublication:
        ...
