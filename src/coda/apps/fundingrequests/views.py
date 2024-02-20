import logging
from typing import Any
from django.http import HttpRequest, HttpResponse

from django.views.generic import DetailView, ListView, TemplateView

from coda.apps.authors.forms import InstitutionForm, PersonForm
from coda.apps.fundingrequests.models import FundingRequest


logger = logging.getLogger(__name__)


class FundingRequestDetailView(DetailView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_detail.html"
    context_object_name = "funding_request"


class FundingRequestListView(ListView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_list.html"
    context_object_name = "funding_requests"
    paginate_by = 10


class FundingRequestCreationWizard(TemplateView):
    template_name = "fundingrequests/fundingrequest_create.html"
    submitter_prefix = "submitter"
    affiliation_prefix = "affiliation"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["submitter_form"] = PersonForm(prefix=self.submitter_prefix)
        ctx["affiliation_form"] = InstitutionForm(prefix=self.affiliation_prefix)
        return ctx

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        submitter_form = PersonForm(request.POST, prefix=self.submitter_prefix)
        affiliation_form = InstitutionForm(request.POST, prefix=self.affiliation_prefix)
        if submitter_form.is_valid():
            submitter_data = submitter_form.cleaned_data
            affiliation_form.full_clean()
            submitter_data[self.affiliation_prefix] = affiliation_form.cleaned_data

            request.session[self.submitter_prefix] = submitter_data

        return HttpResponse("POST request")
