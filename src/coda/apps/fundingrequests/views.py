from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import DetailView, FormView, ListView, TemplateView

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests import services
from coda.apps.fundingrequests.forms import FundingForm
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.forms import PublicationForm
from coda.apps.publications.models import LinkType


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
    template_name = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm
    next = "fundingrequests:create_journal"

    def get_success_url(self) -> str:
        return reverse(self.next)

    def form_valid(self, form: AuthorForm) -> HttpResponse:
        self.request.session["submitter"] = form.to_dto()
        return super().form_valid(form)


class FundingRequestJournalStep(TemplateView):
    template_name = "fundingrequests/fundingrequest_journal.html"
    next = "fundingrequests:create_publication"

    def get_success_url(self) -> str:
        return reverse(self.next)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        if self.request.method != "GET":
            return ctx

        req = self.request.GET
        title = req.get("journal_title")
        if not title:
            return ctx

        journals = Journal.objects.filter(title__icontains=title)
        ctx["journals"] = journals

        return ctx

    def post(self, request: HttpRequest) -> HttpResponse:
        request.session["journal"] = request.POST["journal"]
        return redirect(self.get_success_url())


class FundingRequestPublicationStep(TemplateView):
    template_name = "fundingrequests/fundingrequest_publication.html"

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:create_funding")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["publication_form"] = PublicationForm()
        context["link_types"] = LinkType.objects.all()
        return context

    def post(self, request: HttpRequest) -> HttpResponse:
        form = PublicationForm(self.request.POST)
        if not form.is_valid():
            return redirect(reverse("fundingrequests:create_publication"))

        dto = form.to_dto()
        dto["links"] = [
            {"link_type_id": int(linktype), "value": linkvalue}
            for linktype, linkvalue in zip(
                request.POST.getlist("linktype"), request.POST.getlist("linkvalue"), strict=True
            )
        ]
        self.request.session["publication"] = dto
        return redirect(self.get_success_url())


class FundingRequestFundingStep(FormView[FundingForm]):
    template_name = "fundingrequests/fundingrequest_funding.html"
    form_class = FundingForm

    def form_valid(self, form: FundingForm) -> HttpResponse:
        funding = form.to_dto()
        author_dto: AuthorDto = self.request.session["submitter"]
        publication_dto: PublicationDto = self.request.session["publication"]
        journal = self.request.session["journal"]
        self.funding_request = services.fundingrequest_create(
            author_dto, publication_dto, journal, funding
        )
        return super().form_valid(form)

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.funding_request.pk})
