import logging
from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import fundingrequests
from coda.apps.fundingrequests.views.wizard.parse_store import monograph_dto_from
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    PublisherStep,
    PublisherStepDto,
)
from coda.apps.publications.dto import MonographDto
from coda.apps.wizard import SessionStore, Wizard
from coda.domain.fundingrequest import FundingRequestId


class MonographUpdateMetaView(Wizard):
    store_name = "monograph_request_update_meta"
    steps = [PublicationStep.for_monograph(), PublisherStep()]
    store_factory = SessionStore
    allow_early_complete = True

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def prepare(self, request: HttpRequest) -> None:
        logging.info("Preparing MonographUpdateMetaView")
        store = self.get_store()
        fr = repository.get_monograph_request(self.kwargs["pk"])
        dto = MonographDto.from_monograph(fr.publication)
        store["publication_step"] = dto.to_post_data(exclude={"publisher", "contracts"})
        store["publisher_step"] = PublisherStepDto.from_monograph(fr.publication).to_post_data()
        store.save()

    def complete(self, /, **kwargs: Any) -> None:
        logging.info("Completing MonographUpdateMetaView")
        pk = kwargs["pk"]
        dto = monograph_dto_from(self.get_store())
        fundingrequests.update_publication(FundingRequestId(pk), dto)
