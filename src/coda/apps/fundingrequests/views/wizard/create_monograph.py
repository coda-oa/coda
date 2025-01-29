from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.fundingrequests.views.wizard.parse_store import monograph_dto_from
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStep
from coda.apps.fundingrequests.views.wizard.wizardsteps import FundingStep, ExtraContactStep
from coda.apps.wizard import SessionStore, Wizard
from coda.fundingrequest import FundingRequest, FundingRequestContact


class MonographRequestWizard(LoginRequiredMixin, Wizard):
    store_name = "monograph_request_wizard"
    store_factory = SessionStore
    steps = [PublisherStep(), PublicationStep.for_monograph(), FundingStep(), ExtraContactStep()]

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: dict[str, str]) -> None:
        store = self.get_store()
        extra_contact = FundingRequestContact(
            store["submitter"]["name"], store["submitter"]["email"]
        )
        publication = monograph_dto_from(store).to_monograph()
        cost = PaymentDto(**store["cost"]).to_payment()
        funding = []
        if store.get("funding") is not None:
            funding = [ExternalFundingDto(**f).to_external_funding() for f in store["funding"]]

        funding_request_id = services.fundingrequest_create(
            FundingRequest.new(publication, cost, funding, extra_contact)
        )
        store["funding_request"] = funding_request_id
        store.save()
