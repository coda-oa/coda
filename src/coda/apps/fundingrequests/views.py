from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import formset_factory
from django.forms.formsets import BaseFormSet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.forms import ChooseLabelForm, FundingForm, LabelForm
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.forms import LinkForm, PublicationForm, PublicationFormData
from coda.apps.publications.models import LinkType


class FundingRequestDetailView(LoginRequiredMixin, DetailView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_detail.html"
    context_object_name = "funding_request"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["label_form"] = ChooseLabelForm()
        return context


class FundingRequestListView(LoginRequiredMixin, ListView[FundingRequest]):
    model = FundingRequest
    template_name = "fundingrequests/fundingrequest_list.html"
    context_object_name = "funding_requests"
    paginate_by = 10

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["labels"] = Label.objects.all()
        context["processing_states"] = FundingRequest.PROCESSING_CHOICES
        return context

    def get_queryset(self) -> QuerySet[FundingRequest]:
        return cast(
            QuerySet[FundingRequest],
            repository.search(
                title=self.request.GET.get("title"),
                labels=list(map(int, self.request.GET.getlist("labels"))),
                processing_states=self.request.GET.getlist("processing_status"),
            ),
        )


class FundingRequestSubmitterStep(LoginRequiredMixin, FormView[AuthorForm]):
    template_name = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm
    next = "fundingrequests:create_journal"

    def get_success_url(self) -> str:
        return reverse(self.next)

    def form_valid(self, form: AuthorForm) -> HttpResponse:
        self.request.session["submitter"] = form.to_dto()
        return super().form_valid(form)


class FundingRequestJournalStep(LoginRequiredMixin, TemplateView):
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


class FundingRequestPublicationStep(LoginRequiredMixin, TemplateView):
    template_name = "fundingrequests/fundingrequest_publication.html"

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:create_funding")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["publication_form"] = PublicationForm()
        context["link_types"] = LinkType.objects.all()
        return context

    def post(self, request: HttpRequest) -> HttpResponse:
        publication_form = PublicationForm(self.request.POST)
        link_formset = self.link_formset(request)
        if not (publication_form.is_valid() and link_formset.is_valid()):
            return redirect(reverse("fundingrequests:create_publication"))

        request.session["links"] = [linkform.get_form_data() for linkform in link_formset.forms]
        request.session["publication"] = publication_form.get_form_data()
        return redirect(self.get_success_url())

    def link_formset(self, request: HttpRequest) -> BaseFormSet[LinkForm]:
        types, values = request.POST.getlist("link_type"), request.POST.getlist("link_value")
        links: dict[str, Any] = {
            "form-TOTAL_FORMS": len(types),
            "form-INITIAL_FORMS": 0,
        }

        for i, link in enumerate(zip(types, values)):
            linktype, linkvalue = link
            links[f"form-{i}-link_type"] = linktype
            links[f"form-{i}-link_value"] = linkvalue

        LinkFormSet: type[BaseFormSet[LinkForm]] = formset_factory(LinkForm)
        return LinkFormSet(links)


class FundingRequestFundingStep(LoginRequiredMixin, FormView[FundingForm]):
    template_name = "fundingrequests/fundingrequest_funding.html"
    form_class = FundingForm

    def form_valid(self, form: FundingForm) -> HttpResponse:
        funding = form.to_dto()
        author_dto: AuthorDto = self.request.session["submitter"]
        publication_form_data: PublicationFormData = self.request.session["publication"]
        link_form_data: list[LinkDto] = self.request.session["links"]
        journal = self.request.session["journal"]

        publication_dto = PublicationDto(
            title=publication_form_data["title"],
            publication_state=publication_form_data["publication_state"],
            publication_date=publication_form_data["publication_date"],
            links=link_form_data,
            journal=int(journal),
        )

        self.funding_request = services.fundingrequest_create(author_dto, publication_dto, funding)
        return super().form_valid(form)

    def get_success_url(self, **kwargs: Any) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.funding_request.pk})


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
    funding_request_id = request.POST["fundingrequest"]
    label_id = request.POST["label"]
    services.label_attach(int(funding_request_id), int(label_id))
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request_id}))


@login_required
@require_POST
def detach_label(request: HttpRequest) -> HttpResponse:
    funding_request_id = request.POST["fundingrequest"]
    label_id = request.POST["label"]
    services.label_detach(int(funding_request_id), int(label_id))
    return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request_id}))


@login_required
@require_POST
def approve(request: HttpRequest) -> HttpResponse:
    try:
        funding_request_id = request.POST["fundingrequest"]
        funding_request = repository.get_by_pk(int(funding_request_id))
        funding_request.approve()
        return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request_id}))
    except FundingRequest.DoesNotExist:
        return HttpResponse(status=404)


@login_required
@require_POST
def reject(request: HttpRequest) -> HttpResponse:
    try:
        funding_request_id = request.POST["fundingrequest"]
        funding_request = repository.get_by_pk(int(funding_request_id))
        funding_request.reject()
        return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request_id}))
    except FundingRequest.DoesNotExist:
        return HttpResponse(status=404)
