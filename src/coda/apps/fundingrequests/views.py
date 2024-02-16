from typing import Any

from django.views.generic import DetailView, ListView, TemplateView

from coda.apps.authors.forms import PersonForm
from coda.apps.fundingrequests.forms import FundingRequestForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.forms import LinkForm, PublicationForm


class FundingRequestDetailView(DetailView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_detail.html"
    context_object_name = "funding_request"


class FundingRequestListView(ListView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_list.html"
    context_object_name = "funding_requests"


class FundingRequestCreateView(TemplateView):
    template_name = "fundingrequests/fundingrequest_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["author_form"] = PersonForm()
        ctx["publication_form"] = PublicationForm()
        ctx["link_form"] = LinkForm()
        ctx["fundingrequest_form"] = FundingRequestForm()
        return ctx
