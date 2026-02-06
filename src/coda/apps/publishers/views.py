from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, UpdateView

from coda.apps.blocklist.models import BlockList
from coda.apps.domainqueryset import DomainModelProtocol, DomainQuerySet
from coda.apps.publishers.models import Publisher
from coda.apps.views import EntityListView

from coda.apps.breadcrumbs.decorators import breadcrumb


@dataclass(slots=True, frozen=True)
class PublisherViewModel(DomainModelProtocol[int]):
    id: int
    name: str
    is_blocked: bool


@breadcrumb("Publishers", parent_url_name="publishing:home")
class PublisherListView(LoginRequiredMixin, EntityListView[PublisherViewModel]):
    entity_list_item_template = "publishers/publisher_list_item.html"
    entity_name = "Publishers"
    entity_create_url = "publishing:publishers:create"
    use_generic_entity_filter = True

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.blocklist = BlockList.objects.get()

    def get_entities(self, request: Any) -> Sequence[PublisherViewModel]:
        return DomainQuerySet(
            Publisher.objects.filter(name__icontains=request.GET.get("query", "")).order_by("name"),
            self.publisher_viewmodel,
        )

    def publisher_viewmodel(self, publisher: Publisher) -> PublisherViewModel:
        return PublisherViewModel(
            id=publisher.id,
            name=publisher.name,
            is_blocked=self.is_publisher_blocked(publisher),
        )

    def is_publisher_blocked(self, publisher: Publisher) -> bool:
        return self.blocklist.is_publisher_blocked(publisher)


class PublisherForm(forms.ModelForm[Publisher]):
    class Meta:
        model = Publisher
        fields = "__all__"


@breadcrumb("Create Publisher", parent_url_name="publishing:publishers:list")
class PublisherCreateView(LoginRequiredMixin, CreateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    model = Publisher
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Publisher"
        return context


@breadcrumb("Update Publisher", parent_url_name="publishing:publishers:list")
class PublisherUpdateView(LoginRequiredMixin, UpdateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    model = Publisher
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Publisher"
        return context


@login_required
@require_GET
def publisher_create_modal(request: HttpRequest) -> HttpResponse:
    form = PublisherForm()
    return render(
        request,
        "partials/entity_creation_modal.html",
        {
            "entity_name": "Publisher",
            "form": form,
            "entity_create_url": "publishing:publishers:create_modal_submit",
        },
    )


@login_required
@require_POST
def publisher_create_modal_submit(request: HttpRequest) -> HttpResponse:
    form = PublisherForm(request.POST)

    if form.is_valid():
        publisher = form.save()

        return render(
            request,
            "publishers/partials/publisher_create_success.html",
            {
                "publisher": publisher,
            },
        )
    else:
        return render(
            request,
            "partials/entity_creation_modal.html",
            {
                "entity_name": "Publisher",
                "form": form,
                "entity_create_url": "publishing:publishers:create_modal_submit",
            },
        )
