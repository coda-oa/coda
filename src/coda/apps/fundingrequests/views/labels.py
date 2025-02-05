from collections.abc import Sequence

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.forms import LabelForm
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.views import EntityListView


class LabelCreateView(LoginRequiredMixin, CreateView[Label, LabelForm]):
    template_name = "fundingrequests/labels/label_form.html"
    model = Label
    form_class = LabelForm

    def get_success_url(self) -> str:
        next = self.kwargs.get("next")
        if next:
            return reverse("fundingrequests:detail", kwargs={"pk": next})

        return reverse("fundingrequests:label_list")


label_create_view = LabelCreateView.as_view()


class LabelUpdateView(LoginRequiredMixin, UpdateView[Label, LabelForm]):
    template_name = "fundingrequests/labels/label_form.html"
    model = Label
    form_class = LabelForm

    def get_success_url(self) -> str:
        return reverse("fundingrequests:label_list")


label_update_view = LabelUpdateView.as_view()


class LabelListView(LoginRequiredMixin, EntityListView[Label]):
    entity_name = "Labels"
    entity_create_url = "fundingrequests:label_create"
    entity_list_item_template = "fundingrequests/labels/label_list_item.html"

    def get_entities(self, request: HttpRequest) -> Sequence[Label]:
        return list(Label.objects.all())


label_list_view = LabelListView.as_view()


@login_required
def label_delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    label = get_object_or_404(Label, pk=pk)
    label.delete()
    return HttpResponse()


@login_required
@require_POST
def attach_label(request: HttpRequest) -> HttpResponse:
    funding_request = get_object_or_404(FundingRequest, pk=request.POST["fundingrequest"])
    label = get_object_or_404(Label, pk=request.POST["label"])
    services.label_attach(funding_request, label)
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))


@login_required
@require_POST
def detach_label(request: HttpRequest) -> HttpResponse:
    funding_request = get_object_or_404(FundingRequest, pk=request.POST["fundingrequest"])
    label = get_object_or_404(Label, pk=request.POST["label"])
    services.label_detach(funding_request, label)
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))
