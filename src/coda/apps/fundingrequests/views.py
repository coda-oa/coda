from collections.abc import Callable
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.forms import ChooseLabelForm, LabelForm
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.fundingrequests.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.publications.dto import LinkDto, PublicationDto
from coda.apps.publications.forms import PublicationFormData
from coda.apps.wizard import SessionStore, Store, Wizard


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


class FundingRequestWizard(LoginRequiredMixin, Wizard):
    store_name = "funding_request_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep(), JournalStep(), PublicationStep(), FundingStep()]

    def get_success_url(self) -> str:
        store = self.get_store()
        return reverse("fundingrequests:detail", kwargs={"pk": store["funding_request"]})

    def complete(self, **kwargs: Any) -> None:
        store = self.get_store()
        author_dto: AuthorDto = store["submitter"]
        publication_dto = publication_dto_from_store(store)
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


class UpdatePublicationView(LoginRequiredMixin, Wizard):
    store_name = "update_publication_wizard"
    store_factory = SessionStore
    steps = [PublicationStep(), JournalStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        pk = kwargs["pk"]
        store = self.get_store()
        publication_dto = publication_dto_from_store(store)
        services.fundingrequest_publication_update(pk, publication_dto)


def publication_dto_from_store(store: Store) -> PublicationDto:
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

    return publication_dto


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
