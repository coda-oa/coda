from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.blocklist.models import BlockList
from coda.apps.journals.forms import JournalForm
from coda.apps.journals.models import Journal
from coda.apps.views import SimpleSearchEntityListView


class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal
    slug_field = "eissn"
    slug_url_kwarg = "eissn"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["is_blocked"] = BlockList.objects.get().is_journal_blocked(self.object)
        return ctx


journal_detail_view = JournalDetailView.as_view()


class JournalListView(LoginRequiredMixin, SimpleSearchEntityListView[Journal]):
    model = Journal
    paginate_by = 20
    entity_name = "Journals"
    entity_create_url = "publishing:journals:create"
    entity_list_item_template = "journals/journal_list_item.html"
    search_fields = ["title", "eissn"]
    use_generic_entity_filter = True
    entity_filter_template = "entity_generic_filter.html"
    search_placeholder = "Search by title or eissn..."

journal_list_view = JournalListView.as_view()


class JournalCreateView(LoginRequiredMixin, CreateView[Journal, JournalForm]):
    form_class = JournalForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("publishing:journals:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Journal"
        return context


journal_create_view = JournalCreateView.as_view()


class JournalUpdateView(LoginRequiredMixin, UpdateView[Journal, JournalForm]):
    form_class = JournalForm
    template_name = "generic_form_view.html"
    slug_field = "eissn"
    slug_url_kwarg = "eissn"
    success_url = reverse_lazy("publishing:journals:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Journal"
        return context

    def get_object(self, queryset: QuerySet[Journal] | None = None) -> Journal:
        return Journal.objects.get(eissn=self.kwargs["eissn"])


journal_update_view = JournalUpdateView.as_view()


@login_required
def block_journal(request: HttpRequest, pk: int) -> HttpResponse:
    reason = request.POST.get("reason", "PREDATORY")
    journal = get_object_or_404(Journal, pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.block_journal(journal, reason)

    return cast(HttpResponse, journal_detail_view(request, eissn=journal.eissn))
