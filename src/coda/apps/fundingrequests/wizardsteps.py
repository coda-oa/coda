from typing import Any, TypeVar

from django.forms import BaseFormSet, Form, formset_factory
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.forms import CostForm, ExternalFundingForm
from coda.apps.journals.models import Journal
from coda.apps.publications.dto import LinkDto
from coda.apps.publications.forms import LinkForm, PublicationForm
from coda.apps.publications.models import LinkType
from coda.apps.wizard import FormStep, Step, Store
from coda.authorlist import AuthorList


_TForm = TypeVar("_TForm", bound=Form)


def form_with_post_or_store_data(
    form_type: type[_TForm], request: HttpRequest, store_data: dict[str, Any] | None
) -> _TForm:
    """
    Create a form instance with POST data if matching keys are present, otherwise use stored data.
    If no stored data is present, create an empty form instance.
    """
    if request.POST.keys() & form_type.base_fields.keys():
        return form_type(request.POST)
    elif store_data:
        return form_type(store_data)
    else:
        return form_type()


class SubmitterStep(FormStep):
    template_name: str = "fundingrequests/fundingrequest_submitter.html"
    form_class = AuthorForm

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return super().get_context_data(request, store) | {
            "form": form_with_post_or_store_data(self.form_class, request, store.get("submitter")),
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
        title = request.POST.get("journal_title", None)
        journal_id = store.get("journal", None)
        if title:
            journals = Journal.objects.filter(title__icontains=title)
            ctx["journals"] = journals
            ctx["journal_title"] = title
        elif journal_id:
            selected_journal = get_object_or_404(Journal, pk=journal_id)
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
        return {
            "publication_form": self.get_publication_form(request, store),
            "authors": self.get_authors(request, store),
            "link_types": LinkType.objects.all(),
            "links": self.get_links_context(request, store),
        }

    def get_publication_form(self, request: HttpRequest, store: Store) -> PublicationForm:
        if self.requested_author_preview(request):
            form = PublicationForm(request.POST)
            form.errors.clear()
            return form

        return form_with_post_or_store_data(PublicationForm, request, store.get("publication"))

    def requested_author_preview(self, request: HttpRequest) -> bool:
        return request.POST.get("action") == "parse_authors"

    def get_authors(self, request: HttpRequest, store: Store) -> AuthorList:
        if request.POST.get("authors"):
            return AuthorList.from_str(request.POST.get("authors", ""))
        elif store.get("authors"):
            return AuthorList(store["authors"])
        else:
            return AuthorList()

    def get_links_context(self, request: HttpRequest, store: Store) -> list[LinkDto]:
        if store.get("links"):
            return list(store["links"])
        elif self.has_links(request):
            return self.assemble_link_dtos(request)

        return []

    def has_links(self, request: HttpRequest) -> bool:
        return bool(request.POST.get("link_type") and request.POST.get("link_value"))

    def assemble_link_dtos(self, request: HttpRequest) -> list[LinkDto]:
        return [
            LinkDto(link_type=int(link_type), link_value=link_value)
            for link_type, link_value in zip(
                request.POST.getlist("link_type"), request.POST.getlist("link_value")
            )
        ]

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
        store["authors"] = AuthorList.from_str(request.POST.get("authors", ""))

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
        context["cost_form"] = form_with_post_or_store_data(CostForm, request, store.get("cost"))
        context["funding_form"] = form_with_post_or_store_data(
            ExternalFundingForm, request, store.get("funding")
        )
        return context

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        cost_form = CostForm(request.POST)
        funding_form = ExternalFundingForm(request.POST)
        funding_valid = funding_form.is_valid()
        if not funding_valid:
            funding_valid = not (request.POST.get("organization") or request.POST.get("project_id"))

        return cost_form.is_valid() and funding_valid

    def done(self, request: HttpRequest, store: Store) -> None:
        cost_form = CostForm(request.POST)
        cost_form.full_clean()
        cost = cost_form.to_dto()
        store["cost"] = cost

        funding_form = ExternalFundingForm(request.POST)
        if funding_form.is_valid():
            funding = funding_form.to_dto()
            store["funding"] = funding
        else:
            store["funding"] = None
