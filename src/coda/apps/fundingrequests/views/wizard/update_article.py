from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.fundingrequests.strategies import (
    DatabasePersistenceStrategy,
    FundingRequestPersistenceStrategy,
)
from coda.apps.fundingrequests.views.wizard.steps.extrainformation_step import (
    ExtraInformationStep,
)
from coda.apps.fundingrequests.views.wizard.steps.funding_step import FundingStep
from coda.apps.fundingrequests.views.wizard.steps.journal_step import JournalContractStep
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.publications.dto import ContractYearDto
from coda.apps.wizard import SessionStore, Store, Wizard
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
    UpdatePublicationMetadataCommand,
)
from coda.domain.publication import JournalId


class UpdateExtraInformationStep(ExtraInformationStep):
    """Extra information step with editable reviewer remarks.

    The base step/template are shared with the creation wizards; the
    ``show_reviewer_remarks`` flag gates the field to this update flow.
    """

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return super().get_context_data(request, store) | {
            "page_title": "Additional Information",
            "show_reviewer_remarks": True,
            "reviewer_remarks": self.restore_reviewer_remarks(request, store),
        }

    def restore_reviewer_remarks(self, request: HttpRequest, store: Store) -> str:
        if posted_remarks := request.POST.get("reviewer_remarks"):
            return posted_remarks

        return str(store.get("reviewer_remarks", ""))

    def done(self, request: HttpRequest, store: Store) -> None:
        super().done(request, store)
        # Only overwrite when the form actually posted the field; absence means 'untouched'.
        if "reviewer_remarks" in request.POST:
            store["reviewer_remarks"] = request.POST["reviewer_remarks"]
        store.save()


@breadcrumb("Update Additional Information", parent_url_name="fundingrequests:detail")
class UpdateExtraInformationView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [UpdateExtraInformationStep()]

    def get_strategy(self) -> FundingRequestPersistenceStrategy:
        """Get persistence strategy for this wizard (database by default)."""
        return DatabasePersistenceStrategy(self.kwargs["pk"])

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        strategy = self.get_strategy()
        store = self.get_store()

        contact = ExtraContactDto(**store.get("contact", {}))
        extra_info = ExtraInformationDto(
            request_remarks=store.get("request_remarks", ""),
            extra_contact=contact,
            reviewer_remarks=store.get("reviewer_remarks"),
        )

        strategy.save_extra_information(extra_info)

    def prepare(self, request: HttpRequest) -> None:
        strategy = self.get_strategy()
        store = self.get_store()

        extra_info = strategy.load_extra_information()

        store["request_remarks"] = extra_info.request_remarks
        store["reviewer_remarks"] = extra_info.reviewer_remarks or ""
        if extra_info.extra_contact.name or extra_info.extra_contact.email:
            store["contact"] = {
                "name": extra_info.extra_contact.name,
                "email": extra_info.extra_contact.email,
            }
        store.save()


@breadcrumb("Update Publication Details", parent_url_name="fundingrequests:detail")
class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep.for_article(), JournalContractStep()]
    allow_early_complete = True

    def get_strategy(self) -> FundingRequestPersistenceStrategy:
        """Get persistence strategy for this wizard (database by default)."""
        return DatabasePersistenceStrategy(self.kwargs["pk"])

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        strategy = self.get_strategy()
        store = self.get_store()

        metadata = UpdatePublicationMetadataCommand(**store["publication_step"])
        strategy.save_publication_metadata(metadata)

        if self.index() > 0:
            journal = JournalId(store["journal"])
            contract_dtos = [ContractYearDto(**c) for c in store["contracts"]]
            strategy.save_journal_and_contracts(journal, contract_dtos)

    def prepare(self, request: HttpRequest) -> None:
        strategy = self.get_strategy()
        store = self.get_store()

        dto = strategy.load_publication()

        store["publication_step"] = dto.to_post_data(exclude={"journal", "contracts"})
        store["journal"] = dto.journal.id  # type: ignore
        store["contracts"] = [c.to_post_data() for c in dto.contracts]
        store.save()


@breadcrumb("Update Cost & Funding", parent_url_name="fundingrequests:detail")
class UpdateFundingView(LoginRequiredMixin, Wizard):
    steps = [FundingStep()]
    store_name = "update_funding_wizard"
    store_factory = SessionStore

    def get_strategy(self) -> FundingRequestPersistenceStrategy:
        """Get persistence strategy for this wizard (database by default)."""
        return DatabasePersistenceStrategy(self.kwargs["pk"])

    def get_cancel_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        strategy = self.get_strategy()
        store = self.get_store()

        cost = PaymentDto(**store["cost"])
        funding = []
        if store.get("funding") is not None:
            funding = [ExternalFundingDto(**f) for f in store["funding"]]

        strategy.save_funding(cost, funding)

    def prepare(self, request: HttpRequest) -> None:
        strategy = self.get_strategy()
        store = self.get_store()
        cost, funding = strategy.load_funding()
        store["cost"] = cost.to_post_data()
        store["funding"] = [f.to_post_data() for f in funding]
        store.save()
