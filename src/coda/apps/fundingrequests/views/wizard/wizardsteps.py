import json
from collections.abc import Iterable
from typing import Any, TypeVar

from django.forms import Form
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.forms import CostForm, ExternalFundingForm
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.publications.dto import PublicationMetaDto
from coda.apps.publications.forms import LinkForm, PublicationForm, Vocabularies
from coda.apps.publications.models import LinkType, Vocabulary
from coda.apps.wizard import FormStep, Step, Store
from coda.author import AuthorList

_TForm = TypeVar("_TForm", bound=Form, covariant=True)


def form_with_post_or_store_data(
    form_type: type[_TForm],
    request: HttpRequest,
    store_data: dict[str, Any] | None,
    **kwargs: Any,
) -> _TForm:
    """
    Create a form instance with POST data if matching keys are present, otherwise use stored data.
    If no stored data is present, create an empty form instance.
    """
    if request.POST.keys() & form_type.base_fields.keys():
        return form_type(request.POST, **kwargs)
    elif store_data:
        return form_type(store_data, **kwargs)
    else:
        return form_type(**kwargs)


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
            journals = find_by_title(title)
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
            "authors": list(self.get_authors(request, store)),
            "link_types": LinkType.objects.values("name"),
            "links": self.get_links_context(request, store),
        }

    def get_publication_form(self, request: HttpRequest, store: Store) -> PublicationForm:
        vocabularies = self.get_form_vocabularies(store)

        if self.requested_author_preview(request):
            form = PublicationForm(request.POST, vocabularies=vocabularies)
            form.errors.clear()
            return form

        formdata = self.transform_to_formdata(store)
        return form_with_post_or_store_data(
            PublicationForm, request, formdata, vocabularies=vocabularies
        )

    def get_form_vocabularies(self, store: Store) -> Vocabularies:
        publication_meta: PublicationMetaDto | None = store.get("publication")
        if not publication_meta:
            return Vocabularies()

        subject_vocabulary_id = publication_meta["subject_area_vocabulary"]
        subject_vocabulary = Vocabulary.objects.get(pk=subject_vocabulary_id)
        pub_type_vocabulary_id = publication_meta["publication_type_vocabulary"]
        pub_type_vocabulary = Vocabulary.objects.get(pk=pub_type_vocabulary_id)
        vocabularies = Vocabularies(
            subject_areas=subject_vocabulary.concepts.all(),
            publication_types=pub_type_vocabulary.concepts.all(),
        )

        return vocabularies

    def transform_to_formdata(self, store: Store) -> dict[str, Any]:
        formdata: dict[str, Any] = dict(store.get("publication", {}))
        if formdata:
            formdata["subject_area"] = json.dumps(
                {
                    "concept": formdata["subject_area"],
                    "vocabulary": formdata["subject_area_vocabulary"],
                }
            )
            formdata["publication_type"] = json.dumps(
                {
                    "concept": formdata["publication_type"],
                    "vocabulary": formdata["publication_type_vocabulary"],
                }
            )

        return formdata

    def requested_author_preview(self, request: HttpRequest) -> bool:
        return request.POST.get("action") == "parse_authors"

    def get_authors(self, request: HttpRequest, store: Store) -> AuthorList:
        if request.POST.get("authors"):
            return AuthorList.from_str(request.POST.get("authors", ""))
        elif store.get("authors"):
            return AuthorList(store["authors"])
        else:
            return AuthorList()

    def get_links_context(self, request: HttpRequest, store: Store) -> list[dict[str, Any]]:
        if self.has_links(request):
            return self.assemble_link_dtos(request)
        elif store.get("links"):
            return [{"link": link, "errors": {}} for link in list(store["links"])]

        return []

    def has_links(self, request: HttpRequest) -> bool:
        return bool(request.POST.get("link_type") and request.POST.get("link_value"))

    def assemble_link_dtos(self, request: HttpRequest) -> list[dict[str, Any]]:
        forms = self.link_forms(request)
        for form in forms:
            form.full_clean()

        return [{"link": form.get_form_data(), "errors": form.errors} for form in forms]

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        publication_form = PublicationForm(request.POST)
        link_formset = self.link_forms(request)
        valid = self.all_valid((publication_form, *link_formset))
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        publication_form = PublicationForm(request.POST)
        link_forms = self.link_forms(request)
        self.clean_all((publication_form, *link_forms))

        store["links"] = [linkform.get_form_data() for linkform in link_forms]
        store["publication"] = publication_form.get_form_data()
        store["authors"] = list(AuthorList.from_str(request.POST.get("authors", "")))

    def all_valid(self, forms: Iterable[Form]) -> bool:
        return all(form.is_valid() for form in forms)

    def clean_all(self, forms: Iterable[Form]) -> None:
        for form in forms:
            form.full_clean()

    def link_forms(self, request: HttpRequest) -> Iterable[LinkForm]:
        types, values = request.POST.getlist("link_type"), request.POST.getlist("link_value")
        return [
            LinkForm({"link_type": link_type, "link_value": link_value})
            for link_type, link_value in zip(types, values)
        ]


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
        funding_valid = funding_form.is_valid() or funding_form.is_empty()
        return cost_form.is_valid() and funding_valid

    def done(self, request: HttpRequest, store: Store) -> None:
        cost_form = CostForm(request.POST)
        cost_form.full_clean()
        cost = cost_form.to_dto()
        store["cost"] = cost

        funding_form = ExternalFundingForm(request.POST)
        funding_form.full_clean()
        funding = funding_form.to_dto()
        store["funding"] = funding
