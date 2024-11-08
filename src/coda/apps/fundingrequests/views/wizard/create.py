from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import PaymentDto, ExternalFundingDto
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.wizard import SessionStore, Wizard
from coda.fundingrequest import FundingRequest


class FundingRequestWizard(LoginRequiredMixin, Wizard):
    store_name = "funding_request_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep(), JournalStep(), PublicationStep(), FundingStep()]

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: Any) -> None:
        store = self.get_store()
        author = AuthorDto(**store["submitter"]).to_author()
        publication = publication_dto_from(store).to_publication()
        cost = PaymentDto(**store["cost"]).to_payment()
        funding = []
        if store.get("funding") is not None:
            funding = [ExternalFundingDto(**f).to_external_funding() for f in store["funding"]]

        funding_request_id = services.fundingrequest_create(
            FundingRequest.new(publication, author, cost, funding)
        )
        store["funding_request"] = funding_request_id
        store.save()
