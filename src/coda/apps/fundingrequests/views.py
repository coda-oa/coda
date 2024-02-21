from typing import Any

from django.urls import reverse
from django.http import HttpResponse
from django.views.generic import DetailView, ListView, FormView

from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.forms import PublicationForm


class FundingRequestDetailView(DetailView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_detail.html"
    context_object_name = "funding_request"


class FundingRequestListView(ListView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_list.html"
    context_object_name = "funding_requests"
    paginate_by = 10


class FundingRequestSubmitterStep(FormView[AuthorForm]):
    template_name = "fundingrequests/fundingrequest_create.html"
    form_class = AuthorForm

    def get_success_url(self) -> str:
        return reverse("fundingrequests:create_publication")

    def form_valid(self, form: AuthorForm) -> HttpResponse:
        self.request.session["submitter"] = form.to_dto()
        return super().form_valid(form)


class FundingRequestPublicationStep(FormView[PublicationForm]):
    template_name = "fundingrequests/fundingrequest_publication.html"
    form_class = PublicationForm

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:create_funding")
