from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.views.generic import CreateView, DetailView, FormView, UpdateView

from coda.apps.blocklist.models import BlockList
from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainModelProtocol, DomainQuerySet
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.forms import JournalForm
from coda.apps.journals.models import Journal
from coda.apps.search import words_icontains
from coda.apps.views import EntityListView


@breadcrumb("Journal Detail", parent_url_name="publishing:journals:list", preserve_filters=True)
class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal
    slug_field = "eissn"
    slug_url_kwarg = "eissn"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["is_blocked"] = BlockList.objects.get().is_journal_blocked(self.object)
        ctx["funding_requests"] = (
            FundingRequest.objects.filter(publication__article_journal=self.object)
            .select_related("publication")
            .order_by("-request_date")
        )
        return ctx


journal_detail_view = JournalDetailView.as_view()


@dataclass(slots=True, frozen=True)
class JournalViewModel(DomainModelProtocol[int]):
    id: int
    title: str
    eissn: str
    publisher_name: str
    publisher_url: str
    detail_url: str
    is_blocked: bool
    block_reason_display: str


@breadcrumb("Journals", parent_url_name="publishing:home")
class JournalListView(LoginRequiredMixin, EntityListView[JournalViewModel]):
    model = Journal
    paginate_by = 20
    entity_name = "Journals"
    entity_create_url = "publishing:journals:create"
    entity_list_item_template = "journals/journal_list_item.html"
    search_fields: ClassVar[list[str]] = ["title", "eissn"]
    ordering: ClassVar[list[str]] = []
    use_generic_entity_filter = True
    entity_filter_extra_template = "journals/journal_blocked_checkbox.html"
    search_placeholder = "Search by title or eissn..."
    blocked_journal_ids: set[int]
    block_reasons: dict[int, str]

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        blocked_journals = BlockList.objects.get().blocked_journals()
        self.blocked_journal_ids = set(blocked_journals.values_list("journal_id", flat=True))
        self.block_reasons = {
            entry.journal_id: entry.get_reason_display() for entry in blocked_journals
        }

    def get_entities(self, request: HttpRequest) -> Sequence[JournalViewModel]:
        search_term = request.GET.get("query", "").strip()
        queryset = Journal.objects.select_related("publisher")
        if search_term:
            queryset = queryset.filter(words_icontains(search_term, *self.search_fields))
        if request.GET.get("blocked_only") == "on":
            queryset = queryset.filter(pk__in=self.blocked_journal_ids)
        order_by = self.ordering or self.search_fields
        return DomainQuerySet(queryset.order_by(*order_by), self.journal_viewmodel)

    def journal_viewmodel(self, journal: Journal) -> JournalViewModel:
        return JournalViewModel(
            id=journal.id,
            title=journal.title,
            eissn=journal.eissn,
            publisher_name=journal.publisher.name,
            publisher_url=journal.publisher.get_absolute_url(),
            detail_url=journal.get_absolute_url(),
            is_blocked=journal.id in self.blocked_journal_ids,
            block_reason_display=self.block_reasons.get(journal.id, ""),
        )


journal_list_view = JournalListView.as_view()


@breadcrumb("Create Journal", parent_url_name="publishing:journals:list")
class JournalCreateView(LoginRequiredMixin, CreateView[Journal, JournalForm]):
    form_class = JournalForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("publishing:journals:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Journal"
        return context


journal_create_view = JournalCreateView.as_view()


@breadcrumb("Update Journal", parent_url_name="publishing:journals:detail")
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


class JournalCreateModalView(LoginRequiredMixin, FormView[JournalForm]):
    """Create a journal from the funding-request modal.

    GET renders the creation modal; POST validates and either re-renders the
    modal with errors or returns the success fragment that swaps the created
    journal into the funding request's journal search results.
    """

    form_class = JournalForm
    template_name = "partials/entity_creation_modal.html"
    success_template_name = "journals/partials/journal_create_success.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["entity_name"] = "Journal"
        ctx["entity_create_url"] = "publishing:journals:create_modal"
        if self.request.method == "GET":
            extra_content = render_to_string(
                "journals/partials/journal_modal_publisher_button.html", request=self.request
            )
            ctx["extra_content"] = mark_safe(extra_content)
        return ctx

    def form_valid(self, form: JournalForm) -> HttpResponse:
        journal = form.save()
        return render(
            self.request,
            self.success_template_name,
            {"journal": journal},
        )

    def form_invalid(self, form: JournalForm) -> HttpResponse:
        return self.render_to_response(self.get_context_data(form=form))
