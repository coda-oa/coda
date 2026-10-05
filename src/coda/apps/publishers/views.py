from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, UpdateView

from coda.apps.blocklist.models import BlockList
from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.domainqueryset import DomainModelProtocol, DomainQuerySet
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publishers.models import Publisher
from coda.apps.search import words_icontains
from coda.apps.views import EntityListView


@dataclass(slots=True, frozen=True)
class PublisherViewModel(DomainModelProtocol[int]):
    id: int
    name: str
    is_blocked: bool
    get_absolute_url: str


@breadcrumb("Publishers", parent_url_name="publishing:home")
class PublisherListView(LoginRequiredMixin, EntityListView[PublisherViewModel]):
    entity_list_item_template = "publishers/publisher_list_item.html"
    entity_name = "Publishers"
    entity_create_url = "publishing:publishers:create"
    entity_filter_template = "publishers/publisher_filter.html"
    blocked_publisher_ids: set[int]

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.blocked_publisher_ids = set(
            BlockList.objects.get().blocked_publishers().values_list("publisher_id", flat=True)
        )

    def get_entities(self, request: Any) -> Sequence[PublisherViewModel]:
        search_term = request.GET.get("query", "").strip()
        queryset = Publisher.objects.filter(words_icontains(search_term, "name"))
        if request.GET.get("blocked_only") == "on":
            queryset = queryset.filter(pk__in=self.blocked_publisher_ids)
        return DomainQuerySet(queryset.order_by("name"), self.publisher_viewmodel)

    def publisher_viewmodel(self, publisher: Publisher) -> PublisherViewModel:
        return PublisherViewModel(
            id=publisher.id,
            name=publisher.name,
            is_blocked=publisher.id in self.blocked_publisher_ids,
            get_absolute_url=publisher.get_absolute_url(),
        )


@breadcrumb("Publisher Detail", parent_url_name="publishing:publishers:list", preserve_filters=True)
class PublisherDetailView(LoginRequiredMixin, DetailView[Publisher]):
    model = Publisher

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["journals"] = self.object.journals.only("title", "eissn", "publisher_id").order_by(
            "title"
        )
        ctx["is_blocked"] = BlockList.objects.get().is_publisher_blocked(self.object)
        ctx["funding_requests"] = (
            FundingRequest.objects.filter(
                Q(publication__article_journal__publisher=self.object)
                | Q(publication__monograph_publisher=self.object)
            )
            .select_related("publication")
            .order_by("-request_date")
        )
        return ctx


class PublisherForm(forms.ModelForm[Publisher]):
    class Meta:
        model = Publisher
        fields = "__all__"


@breadcrumb("Create Publisher", parent_url_name="publishing:publishers:list")
class PublisherCreateView(LoginRequiredMixin, CreateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Publisher"
        return context


@breadcrumb("Update Publisher", parent_url_name="publishing:publishers:list")
class PublisherUpdateView(LoginRequiredMixin, UpdateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    queryset = Publisher.objects.all()
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Publisher"
        return context


@login_required
@require_GET
def publisher_create_modal(request: HttpRequest) -> HttpResponse:
    return _render_publisher_modal(request, PublisherForm(), request.GET.get("context", ""))


@login_required
@require_POST
def publisher_create_modal_submit(request: HttpRequest) -> HttpResponse:
    form = PublisherForm(request.POST)
    context_param = request.GET.get("context", "")

    if form.is_valid():
        publisher = form.save()
        return render(
            request,
            _get_success_template(context_param),
            {"publisher": publisher},
        )

    return _render_publisher_modal(request, form, context_param)


def _render_publisher_modal(
    request: HttpRequest, form: PublisherForm, context_param: str
) -> HttpResponse:
    submit_url = reverse("publishing:publishers:create_modal_submit")
    if context_param:
        submit_url += f"?{urlencode({'context': context_param})}"

    target_wrapper = (
        "nested-entity-creation-modal-wrapper"
        if context_param == "journal_modal"
        else "entity-creation-modal-wrapper"
    )

    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": "Publisher",
            "form": form,
            "entity_create_url_path": submit_url,
            "modal_target_wrapper": target_wrapper,
        },
    )


def _get_success_template(context_param: str) -> str:
    if context_param == "journal_modal":
        template = "publishers/partials/publisher_create_success_journal_context.html"
    else:
        template = "publishers/partials/publisher_create_success.html"
    return template
