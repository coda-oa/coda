from collections.abc import Sequence
from typing import Any

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.publishers.models import Publisher
from coda.apps.views import EntityListView


class PublisherListView(LoginRequiredMixin, EntityListView[Publisher]):
    entity_list_item_template = "publishers/publisher_list_item.html"
    entity_name = "Publishers"
    entity_create_url = "publishing:publishers:create"
    use_generic_entity_filter = True

    def get_entities(self, request: Any) -> Sequence[Publisher]:
        return DomainQuerySet(
            Publisher.objects.filter(name__icontains=request.GET.get("query", "")).order_by("name"),
            lambda p: p,
        )


class PublisherForm(forms.ModelForm[Publisher]):
    class Meta:
        model = Publisher
        fields = "__all__"


class PublisherCreateView(LoginRequiredMixin, CreateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    model = Publisher
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Publisher"
        return context


class PublisherUpdateView(LoginRequiredMixin, UpdateView[Publisher, PublisherForm]):
    template_name = "generic_form_view.html"
    model = Publisher
    form_class = PublisherForm
    success_url = reverse_lazy("publishing:publishers:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Publisher"
        return context
