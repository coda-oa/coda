import datetime
from typing import Any

from django.urls import reverse
from django.http import HttpResponse
from django.views.generic import DetailView, ListView, FormView

from coda.apps.authors.forms import AuthorForm
from coda.apps.authors.models import Author, AuthorDto
from coda.apps.fundingrequests.forms import FundingForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.models import Journal
from coda.apps.publications.forms import PublicationForm
from coda.apps.publications.models import Publication, PublicationDto


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

    def form_valid(self, form: PublicationForm) -> HttpResponse:
        self.request.session["publication"] = form.to_dto()
        return super().form_valid(form)


class FundingRequestFundingStep(FormView[FundingForm]):
    template_name = "fundingrequests/fundingrequest_funding.html"
    form_class = FundingForm

    def form_valid(self, form: FundingForm) -> HttpResponse:
        funding = form.to_dto()
        author_dto: AuthorDto = self.request.session["submitter"]
        publication_dto: PublicationDto = self.request.session["publication"]
        author = Author.create_from_dto(author_dto)
        journal = Journal.objects.get(pk=publication_dto["journal"])
        publication = Publication.objects.create(
            title=publication_dto["title"],
            publication_state=publication_dto["publication_state"],
            publication_date=datetime.date.fromisoformat(publication_dto["publication_date"]),
            submitting_author=author,
            journal=journal,
        )

        self.funding_request = FundingRequest.objects.create(
            submitter=author,
            publication=publication,
            estimated_cost=funding["estimated_cost"],
            estimated_cost_currency=funding["estimated_cost_currency"],
        )
        return super().form_valid(form)

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.funding_request.pk})
