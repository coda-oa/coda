from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel


from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView


from typing import Any


class FundingRequestDetailView(LoginRequiredMixin, DetailView[FundingRequestModel]):
    model = FundingRequestModel
    template_name = "fundingrequests/fundingrequest_detail.html"
    context_object_name = "funding_request"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["label_form"] = ChooseLabelForm()
        return context
