import logging
from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from coda.apps.fundingrequests import repository
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.fundingrequest.dto.commands import UpdatePublicationMetadataCommand
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    PublisherStep,
    PublisherStepDto,
)
from coda.apps.publications.dto import MonographDto
from coda.apps.wizard import SessionStore, Wizard
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Update Publication Details", parent_url_name="fundingrequests:detail")
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
        store = self.get_store()
        pk = FundingRequestId(kwargs["pk"])

        # Always update metadata from PublicationStep
        metadata = UpdatePublicationMetadataCommand(**store["publication_step"])
        fundingrequests.update_publication_metadata(pk, metadata)

        # Update publisher + contracts only if PublisherStep was completed
        if self.index() > 0:  # PublisherStep is at index 1
            publisher_step = PublisherStepDto(**store["publisher_step"])
            publisher = PublisherId(publisher_step.publisher)
            fundingrequests.update_publication_publisher_and_contracts(
                pk, publisher, publisher_step.contracts
            )
