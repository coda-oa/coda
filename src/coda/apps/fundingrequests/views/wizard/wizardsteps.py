from collections.abc import Iterable
from typing import Any, TypeVar

from django.forms import Form
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.forms import ContractFormset, ExternalFundingFormset, PaymentForm
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.publications.dto import PublicationStepDto
from coda.apps.publications.forms import CorrespondingAuthorForm, LinkForm, PublicationForm
from coda.apps.publications.models import LinkType
from coda.apps.wizard import FormStep, Step, Store
from coda.author import AuthorList

_TForm = TypeVar("_TForm", bound=Form, covariant=True)


def form_posted(request: HttpRequest, form_type: type[Form]) -> bool:
    return bool(request.POST.keys() & form_type.base_fields.keys())


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
    if form_posted(request, form_type):
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
        store["submitter"] = form.to_dto().to_post_data()


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

        if request.POST.get("total_forms"):
            ctx["contract_formset"] = ContractFormset(request.POST)
        else:
            contracts = store.get("contracts", [])
            ctx["contract_formset"] = ContractFormset.from_data(
                [{"contract": cid} for cid in contracts]
            )

        return ctx

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return bool(request.POST.get("journal"))

    def done(self, request: HttpRequest, store: Store) -> None:
        contract_formset = ContractFormset(request.POST)
        contracts = [c["contract"].pk for c in contract_formset.data]

        store["journal"] = request.POST["journal"]
        store["contracts"] = contracts
        store.save()


class PublicationStep(Step):
    template_name: str = "fundingrequests/fundingrequest_publication.html"

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return {
            "author_form": self.get_author_form(request, store),
            "publication_form": self.get_publication_form(request, store),
            "authors": list(self.get_authors(request, store)),
            "link_types": LinkType.objects.values("name"),
            "links": self.get_links_context(request, store),
        }

    def get_author_form(self, request: HttpRequest, store: Store) -> CorrespondingAuthorForm:
        form_prefix = "corresponding_author"
        field_names = {
            f"{form_prefix}-{field}" for field in CorrespondingAuthorForm.base_fields.keys()
        }
        if field_names & request.POST.keys():
            return CorrespondingAuthorForm(request.POST, prefix=form_prefix)
        elif store.get("publication_step"):
            dto = AuthorDto(**store["publication_step"]["corresponding_author"])
            data = dto.to_post_data(prefix=form_prefix)
            return CorrespondingAuthorForm(data, prefix=form_prefix)
        elif store.get("submitter"):
            dto = AuthorDto(**store["submitter"])
            author = dto.to_author()
            if author.is_corresponding_author():
                data = dto.to_post_data(prefix=form_prefix)
                return CorrespondingAuthorForm(data, prefix=form_prefix)

        return CorrespondingAuthorForm(prefix=form_prefix)

    def get_publication_form(self, request: HttpRequest, store: Store) -> PublicationForm:
        if self.requested_author_preview(request):
            form = PublicationForm(request.POST)
            form.errors.clear()
            return form

        step_dto = store.get("publication_step")
        if form_posted(request, PublicationForm):
            return PublicationForm(request.POST)
        elif step_dto:
            return PublicationForm.from_dto(PublicationStepDto(**step_dto).meta)
        else:
            return PublicationForm()

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
        corresponding_author_form = self.get_author_form(request, store)
        publication_form = PublicationForm(request.POST)
        link_formset = self.link_forms(request)
        valid = self.all_valid((corresponding_author_form, publication_form, *link_formset))
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        publication_form = PublicationForm(request.POST)
        link_forms = self.link_forms(request)
        self.clean_all((publication_form, *link_forms))

        store["publication_step"] = PublicationStepDto(
            corresponding_author=CorrespondingAuthorForm(
                request.POST, prefix="corresponding_author"
            ).to_dto(),
            meta=publication_form.to_dto(),
            authors=list(AuthorList.from_str(request.POST.get("authors", ""))),
            links=[linkform.get_form_data() for linkform in link_forms],
        ).to_post_data()
        store.save()

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
        context["cost_form"] = form_with_post_or_store_data(PaymentForm, request, store.get("cost"))
        context["funding_formset"] = self._restore_formset(request, store)
        return context

    def _restore_formset(self, request: HttpRequest, store: Store) -> ExternalFundingFormset:
        if request.POST.get("total_forms"):
            return ExternalFundingFormset(request.POST)
        elif store.get("funding"):
            return ExternalFundingFormset.from_data(store["funding"])
        else:
            return ExternalFundingFormset()

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        cost_form = PaymentForm(request.POST)
        funding_formset = ExternalFundingFormset(request.POST)
        funding_valid = funding_formset.is_valid() or funding_formset.is_empty()
        return cost_form.is_valid() and funding_valid

    def done(self, request: HttpRequest, store: Store) -> None:
        cost_form = PaymentForm(request.POST)
        cost_form.full_clean()
        cost = cost_form.to_dto()
        store["cost"] = cost.to_post_data()

        funding_formset = ExternalFundingFormset(request.POST)
        dto = funding_formset.to_dto_list()
        store["funding"] = list(d.to_post_data() for d in dto) if dto else None
        store.save()
