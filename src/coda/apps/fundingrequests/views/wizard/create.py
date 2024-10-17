from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

from coda.apps.authors.dto import parse_author
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import parse_external_funding, parse_payment
from coda.apps.fundingrequests.views.wizard.parse_store import publication_dto_from
from coda.apps.fundingrequests.views.wizard.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.publications.dto import parse_publication
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
        author = parse_author(store["submitter"])
        publication = parse_publication(publication_dto_from(store))
        cost = parse_payment(store["cost"])
        funding = (
            [parse_external_funding(f) for f in store["funding"]] if store.get("funding") else []
        )

        funding_request_id = services.fundingrequest_create(
            FundingRequest.new(publication, author, cost, funding)
        )
        store["funding_request"] = funding_request_id
