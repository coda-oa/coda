import datetime
from collections.abc import Callable
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from coda.apps.authors.dto import author_dto_from_model, parse_author
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.authors.services import author_update
from coda.apps.fundingrequests import repository, services
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.forms import ChooseLabelForm, LabelForm
from coda.apps.fundingrequests.models import FundingRequest, Label
from coda.apps.fundingrequests.wizardsteps import (
    FundingStep,
    JournalStep,
    PublicationStep,
    SubmitterStep,
)
from coda.apps.publications.dto import (
    LinkDto,
    PublicationDto,
    parse_publication,
    publication_dto_from_model,
)
from coda.apps.publications.forms import PublicationFormData
from coda.apps.publications.services import publication_update
from coda.apps.wizard import SessionStore, Store, Wizard
from coda.author import AuthorId, AuthorList
from coda.publication import PublicationId


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
        author = parse_author(store["submitter"])
        publication = parse_publication(publication_dto_from_store(store))
        cost = store["cost"]
        funding = store["funding"]

        funding_request = services.fundingrequest_create(author, publication, funding, cost)
        store["funding_request"] = funding_request.pk


class UpdateSubmitterView(LoginRequiredMixin, Wizard):
    store_name = "update_submitter_wizard"
    store_factory = SessionStore
    steps = [SubmitterStep()]

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequest, pk=self.kwargs["pk"])
        submitter_id = AuthorId(cast(AuthorModel, fr.submitter).pk)
        author = parse_author(store["submitter"], submitter_id)
        author_update(author)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequest, pk=self.kwargs["pk"])
        if fr.submitter:
            store["submitter"] = author_dto_from_model(fr.submitter) | {"id": fr.submitter.pk}
            store.save()


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
        funding_request = get_object_or_404(FundingRequest, pk=pk)
        publication = parse_publication(
            publication_dto, id=PublicationId(funding_request.publication.pk)
        )
        publication_update(publication)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequest, pk=self.kwargs["pk"])
        dto = publication_dto_from_model(fr.publication)
        store["publication"] = dto
        store["authors"] = list(dto["authors"])
        store["journal"] = fr.publication.journal.pk
        store["links"] = dto["links"]
        store.save()


class UpdateFundingView(LoginRequiredMixin, Wizard):
    steps = [FundingStep()]
    store_name = "update_funding_wizard"
    store_factory = SessionStore

    def get_success_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.kwargs["pk"]})

    def complete(self, /, **kwargs: Any) -> None:
        store = self.get_store()
        funding = store.get("funding")
        cost = store["cost"]
        fr = get_object_or_404(FundingRequest, pk=self.kwargs["pk"])
        services.fundingrequest_funding_update(fr, funding, cost)

    def prepare(self, request: HttpRequest) -> None:
        store = self.get_store()
        fr = get_object_or_404(FundingRequest, pk=self.kwargs["pk"])
        store["cost"] = CostDto(
            estimated_cost=float(fr.estimated_cost),
            estimated_cost_currency=fr.estimated_cost_currency,
            payment_method=fr.payment_method,
        )
        if fr.external_funding:
            store["funding"] = ExternalFundingDto(
                organization=fr.external_funding.organization.pk,
                project_id=fr.external_funding.project_id,
                project_name=fr.external_funding.project_name,
            )
        store.save()


def publication_dto_from_store(store: Store) -> PublicationDto:
    publication_form_data: PublicationFormData = store["publication"]
    link_form_data: list[LinkDto] = store["links"]
    journal = store["journal"]
    authors = AuthorList(store["authors"])
    publication_dto = PublicationDto(
        title=publication_form_data["title"],
        authors=authors,
        license=publication_form_data["license"],
        open_access_type=publication_form_data["open_access_type"],
        publication_state=publication_form_data["publication_state"],
        publication_date=_parse_date(publication_form_data),
        links=link_form_data,
        journal=int(journal),
    )

    return publication_dto


def _parse_date(publication_form_data: PublicationFormData) -> datetime.date | None:
    maybe_date = publication_form_data["publication_date"]
    return datetime.date.fromisoformat(maybe_date) if maybe_date else None


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


def fundingrequest_action(
    action: Callable[[FundingRequest], None],
) -> Callable[[HttpRequest], HttpResponse]:
    @login_required
    @require_POST
    def post(request: HttpRequest) -> HttpResponse:
        try:
            funding_request = get_object_or_404(FundingRequest, pk=request.POST["fundingrequest"])
            action(funding_request)
            return redirect(reverse("fundingrequests:detail", kwargs={"pk": funding_request.pk}))
        except FundingRequest.DoesNotExist:
            return HttpResponse(status=404)

    return post


approve = fundingrequest_action(FundingRequest.approve)
reject = fundingrequest_action(FundingRequest.reject)
open = fundingrequest_action(FundingRequest.open)
