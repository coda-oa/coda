from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.contexts.fundingrequest.services.panter import (
    fetch_journal_pricing,
    journal_info,
)


class ApcPanelView(LoginRequiredMixin, DetailView[FundingRequestModel]):
    model = FundingRequestModel
    template_name = "fundingrequests/partials/apc_panel.html"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "publication__article_journal__publisher"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.object.publication.article_journal if self.object.publication else None
        context["journal"] = journal
        if journal is not None:
            context["journal_info"] = journal_info(journal.eissn)
            context["pricing"] = fetch_journal_pricing(journal.eissn)
        return context
