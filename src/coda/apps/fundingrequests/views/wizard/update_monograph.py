import logging
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests.strategies import (
    DatabasePersistenceStrategy,
    FundingRequestPersistenceStrategy,
)
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import (
    PublisherStep,
    PublisherStepDto,
)
from coda.apps.wizard import SessionStore, Wizard
from coda.contexts.fundingrequest.dto.commands import UpdatePublicationMetadataCommand
from coda.domain.contract import PublisherId


@breadcrumb("Update Publication Details", parent_url_name="fundingrequests:detail")
class MonographUpdateMetaView(LoginRequiredMixin, Wizard):
    store_name = "monograph_request_update_meta"
    steps = [PublicationStep.for_monograph(), PublisherStep()]
    store_factory = SessionStore
    allow_early_complete = True

    def get_strategy(self) -> FundingRequestPersistenceStrategy:
        """Get persistence strategy for this wizard (database by default)."""
        return DatabasePersistenceStrategy(self.kwargs["pk"])

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def prepare(self, request: HttpRequest) -> None:
        logging.info("Preparing MonographUpdateMetaView")
        strategy = self.get_strategy()
        store = self.get_store()

        from coda.apps.publications.dto import MonographDto

        dto = strategy.load_publication()

        store["publication_step"] = dto.to_post_data(exclude={"publisher", "contracts"})

        if isinstance(dto, MonographDto):
            store["publisher_step"] = PublisherStepDto(
                publisher=dto.publisher, contracts=dto.contracts
            ).to_post_data()

        store.save()

    def complete(self, /, **kwargs: Any) -> None:
        logging.info("Completing MonographUpdateMetaView")
        strategy = self.get_strategy()
        store = self.get_store()

        metadata = UpdatePublicationMetadataCommand(**store["publication_step"])
        strategy.save_publication_metadata(metadata)

        if self.index() > 0:
            publisher_step = PublisherStepDto(**store["publisher_step"])
            publisher = PublisherId(publisher_step.publisher)
            strategy.save_publisher_and_contracts(publisher, publisher_step.contracts)
