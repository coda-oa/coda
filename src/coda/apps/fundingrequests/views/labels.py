from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView

from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.forms import LabelForm
from coda.apps.fundingrequests.models import FundingRequest, Label


class LabelCreateView(LoginRequiredMixin, CreateView[Label, LabelForm]):
    template_name = "fundingrequests/forms/label_form.html"
    model = Label
    form_class = LabelForm

    def get(self, request: HttpRequest, *args: str, **kwargs: Any) -> HttpResponse:
        request.session["next"] = kwargs["next"]
        return super().get(request, *args, **kwargs)

    def get_success_url(self) -> str:
        next = self.request.session.pop("next")
        return reverse("fundingrequests:detail", kwargs={"pk": next})


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
