import abc
from typing import Generic, TypeVar, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse, reverse_lazy

from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.apps.wizard import Store, Wizard
from coda.domain.fundingrequest.identity import PublicFundingRequestId

TPublicationDto = TypeVar("TPublicationDto", PublicationDto, MonographDto)


class FundingRequestCreationWizard(LoginRequiredMixin, Wizard, abc.ABC, Generic[TPublicationDto]):
    cancel_url = cast(str, reverse_lazy("fundingrequests:list"))
    request_id_generator = PublicFundingRequestId.create

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: dict[str, str]) -> None:
        store = self.get_store()
        publication = self.parse_publication(store)
        cost = PaymentDto(**store["cost"])
        funding = self.parse_funding(store)
        extra_information = ExtraInformationDto(
            extra_contact=self.parse_contact(store),
            request_remarks=store.get("request_remarks", ""),
        )
        funding_request_id = fundingrequests.create_fundingrequest(
            CreateFundingRequestDto(
                publication=publication,
                payment=cost,
                funding=funding,
                extra_information=extra_information,
            ),
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
