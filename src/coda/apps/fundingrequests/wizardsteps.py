from typing import Any

from django.forms import BaseFormSet, formset_factory
from django.http import HttpRequest

from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.forms import CostForm, ExternalFundingForm
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.forms import LinkForm, PublicationForm
from coda.apps.publications.models import LinkType
from coda.apps.wizard import FormStep, Step, Store


class SubmitterStep(FormStep):
    template_name: str = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        form_data = store.get("submitter") or (request.POST if request.method == "POST" else None)
        return super().get_context_data(request, store) | {
            "form": self.form_class(form_data),
            "submitter": store.get("submitter"),
        }

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        form = AuthorForm(request.POST)
        valid = form.is_valid()
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        form = AuthorForm(request.POST)
        form.full_clean()
        store["submitter"] = form.to_dto()


class JournalStep(Step):
    template_name: str = "fundingrequests/fundingrequest_journal.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        ctx = super().get_context_data(request, store)
        if title := request.POST.get("journal_title"):
            journals = Journal.objects.filter(title__icontains=title)
            ctx["journals"] = journals
            ctx["journal_title"] = title
        elif journal_id := store.get("selected_journal", None):
            selected_journal = Journal.objects.get(pk=journal_id)
            ctx["selected_journal"] = selected_journal
            ctx["journal_title"] = selected_journal.title
            ctx["journals"] = [selected_journal]

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
        context["cost_form"] = CostForm(store.get("cost"))
        context["funding_form"] = ExternalFundingForm(store.get("funding"))
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
