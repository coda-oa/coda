from collections.abc import Callable
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
from django.views.generic import CreateView, DetailView, ListView

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.forms import (
    ChooseLabelForm,
    CostForm,
    ExternalFundingForm,
    LabelForm,
)
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.forms import LinkForm, PublicationForm, PublicationFormData
from coda.apps.publications.models import LinkType
from coda.apps.wizard import FormStep, SessionStore, Step, Store, Wizard


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
        search_type = self.request.GET.get("search_type")
        if search_type in ["title", "submitter"]:
            search_args = {search_type: self.request.GET.get("search_term")}
        else:
            search_args = {}

        return cast(
            QuerySet[FundingRequest],
            repository.search(
                **search_args,
                labels=list(map(int, self.request.GET.getlist("labels"))),
                processing_states=self.request.GET.getlist("processing_status"),
            ),
        )


class SubmitterStep(FormStep):
    template_name: str = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        form_data = store.get("submitter") or (request.POST if request.method == "POST" else None)
        return super().get_context_data(request, store) | {"form": self.form_class(form_data)}

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        form = AuthorForm(request.POST)
        valid = form.is_valid()
        print("valid", valid)
        print(form.errors)
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        form = AuthorForm(request.POST)
        form.full_clean()
        store["submitter"] = form.to_dto()


class JournalStep(Step):
    template_name: str = "fundingrequests/fundingrequest_journal.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        title = request.POST.get("journal_title")
        if not title:
            return ctx

        journals = Journal.objects.filter(title__icontains=title)
        ctx["journals"] = journals

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return bool(request.POST.get("journal"))

    def done(self, request: HttpRequest, store: Store) -> None:
        store["journal"] = request.POST["journal"]


class PublicationStep(Step):
    template_name: str = "fundingrequests/fundingrequest_publication.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        context = super().get_context_data(request, store)
        context["publication_form"] = PublicationForm(store.get("publication"))
        context["link_types"] = LinkType.objects.all()

        if store.get("links"):
            context["links"] = list(store["links"])

        if self.has_links(request):
            context["links"] = self.assemble_link_dtos(request)

        return context

    def assemble_link_dtos(self, request: HttpRequest) -> list[LinkDto]:
        return [
            LinkDto(link_type=int(link_type), link_value=link_value)
            for link_type, link_value in zip(
                request.POST.getlist("link_type"), request.POST.getlist("link_value")
            )
        ]

    def has_links(self, request: HttpRequest) -> bool:
        return bool(request.POST.get("link_type") and request.POST.get("link_value"))

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        publication_form = PublicationForm(request.POST)
        link_formset = self.link_formset(request)
        return publication_form.is_valid() and link_formset.is_valid()

    def done(self, request: HttpRequest, store: Store) -> None:
        publication_form = PublicationForm(request.POST)
        publication_form.full_clean()

        link_formset = self.link_formset(request)
        link_formset.full_clean()

        store["links"] = [linkform.get_form_data() for linkform in link_formset.forms]
        store["publication"] = publication_form.get_form_data()

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


class FundingStep(Step):
    template_name: str = "fundingrequests/fundingrequest_funding.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        context = super().get_context_data(request, store)
        context["cost_form"] = CostForm()
        context["funding_form"] = ExternalFundingForm()
        return context

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        cost_form = CostForm(request.POST)
        funding_form = ExternalFundingForm(request.POST)
        return cost_form.is_valid() and funding_form.is_valid()

    def done(self, request: HttpRequest, store: Store) -> None:
        cost_form = CostForm(request.POST)
        cost_form.full_clean()
        cost = cost_form.to_dto()

        funding_form = ExternalFundingForm(request.POST)
        funding_form.full_clean()
        funding = funding_form.to_dto()
        store["cost"] = cost
        store["funding"] = funding


class FundingRequestWizard(LoginRequiredMixin, Wizard):
    store_name = "funding_request_wizard"
    store_factory = SessionStore
    steps = [
        SubmitterStep(),
        JournalStep(),
        PublicationStep(),
        FundingStep(),
    ]

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: Any) -> None:
        store = self.get_store()
        author_dto: AuthorDto = store["submitter"]
        publication_form_data: PublicationFormData = store["publication"]
        link_form_data: list[LinkDto] = store["links"]
        journal = store["journal"]
        publication_dto = PublicationDto(
            title=publication_form_data["title"],
            publication_state=publication_form_data["publication_state"],
            publication_date=publication_form_data["publication_date"],
            links=link_form_data,
            journal=int(journal),
        )
        cost = store["cost"]
        funding = store["funding"]

        funding_request = services.fundingrequest_create(author_dto, publication_dto, funding, cost)
        store["funding_request"] = funding_request.pk


class UpdateSubmitterView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        pk = kwargs["pk"]
        store = self.get_store()
        author_dto: AuthorDto = store["submitter"]
        services.fundingrequest_submitter_update(pk, author_dto)


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


def fundingrequest_action(
    action: Callable[[FundingRequest], None],
) -> Callable[[HttpRequest], HttpResponse]:
    @login_required
    @require_POST
    def post(request: HttpRequest) -> HttpResponse:
        try:
            funding_request_id = request.POST["fundingrequest"]
            funding_request = repository.get_by_pk(int(funding_request_id))
            action(funding_request)
            return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request_id}))
        except FundingRequest.DoesNotExist:
            return HttpResponse(status=404)

    return post


approve = fundingrequest_action(FundingRequest.approve)
reject = fundingrequest_action(FundingRequest.reject)
open = fundingrequest_action(FundingRequest.open)
