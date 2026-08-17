from typing import Any, TypeVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Model, QuerySet
from django.views.generic import DetailView

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.journals.models import Journal
from coda.contexts.fundingrequest.services.panter import (
    fetch_journal_pricing,
    journal_info,
)

ModelT = TypeVar("ModelT", bound=Model)


class BaseApcPanelView(LoginRequiredMixin, DetailView[ModelT]):
    template_name = "fundingrequests/partials/apc_panel.html"

    def get_journal(self) -> Journal | None:
        raise NotImplementedError

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        journal = self.get_journal()
        context["journal"] = journal
        if journal is not None:
            context["journal_info"] = journal_info(journal.eissn)
            context["pricing"] = fetch_journal_pricing(journal.eissn)
        return context


class ApcPanelView(BaseApcPanelView[FundingRequestModel]):
    model = FundingRequestModel

    def get_queryset(self) -> QuerySet[FundingRequestModel]:
        return super().get_queryset().select_related("publication__article_journal__publisher")

    def get_journal(self) -> Journal | None:
        return self.object.publication.article_journal if self.object.publication else None


class ApcPanelByJournalView(BaseApcPanelView[Journal]):
    model = Journal

    def get_queryset(self) -> QuerySet[Journal]:
        return super().get_queryset().select_related("publisher")

    def get_journal(self) -> Journal | None:
        return self.object
