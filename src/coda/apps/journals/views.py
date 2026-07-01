from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.views.generic import CreateView, DetailView, UpdateView
from django.views.decorators.http import require_GET, require_POST

from coda.apps.blocklist.models import BlockList
from coda.apps.journals.forms import JournalForm
from coda.apps.journals.models import Journal
from coda.apps.views import SimpleSearchEntityListView

from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Journal Detail", parent_url_name="publishing:journals:list", preserve_filters=True)
class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal
    slug_field = "eissn"
    slug_url_kwarg = "eissn"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["is_blocked"] = BlockList.objects.get().is_journal_blocked(self.object)
        return ctx


journal_detail_view = JournalDetailView.as_view()


@breadcrumb("Journals", parent_url_name="publishing:home")
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


@login_required
@require_GET
def journal_create_modal(request: HttpRequest) -> HttpResponse:
    form = JournalForm()

    extra_content = render_to_string(
        "journals/partials/journal_modal_publisher_button.html", request=request
    )

    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": "Journal",
            "form": form,
            "entity_create_url": "publishing:journals:create_modal_submit",
            "extra_content": mark_safe(extra_content),
        },
    )


@login_required
@require_POST
def journal_create_modal_submit(request: HttpRequest) -> HttpResponse:
    form = JournalForm(request.POST)

    if form.is_valid():
        journal = form.save()

        return render(
            request,
            "journals/partials/journal_create_success.html",
            {
                "journal": journal,
            },
        )
    else:
        return render(
            request,
            "partials/entity_creation_modal.html",
            {
                "entity_name": "Journal",
                "form": form,
                "entity_create_url": "publishing:journals:create_modal_submit",
            },
        )
