from collections.abc import Iterable
from typing import Any, Literal, Protocol, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorFormset
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.publications.dto import PublicationMetaDto
from coda.apps.publications.forms import LinkForm, PublicationForm
from coda.apps.publications.models import LinkType
from coda.apps.wizard import Store, TemplateStep
from coda.contexts.fundingrequest.dto.commands import UpdatePublicationMetadataCommand
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.fundingrequest.services.allowed_vocabularies import AllowedConcepts
from coda.domain.author import AuthorNames


class FormLike(Protocol):
    def is_valid(self) -> bool: ...

    def full_clean(self) -> None: ...


class PublicationStep(TemplateStep):
    template_name: str = "fundingrequests/fundingrequest_publication.html"
    publication_kind: Literal["article", "monograph"]

    @classmethod
    def for_article(cls) -> "PublicationStep":
        return cls("article")

    @classmethod
    def for_monograph(cls) -> "PublicationStep":
        return cls("monograph")

    def __init__(self, publication_kind: Literal["article", "monograph"] = "article") -> None:
        self.publication_kind = publication_kind

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return {
            "author_formset": self.get_author_formset(request, store),
            "publication_form": self.get_publication_form(request, store),
            "authors": list(self.get_authors(request, store)),
            "link_types": LinkType.objects.values("name"),
            "links": self.get_links_context(request, store),
        }

    def get_author_formset(self, request: HttpRequest, store: Store) -> AuthorFormset:
        relevant_authors = store.get("publication_step", {}).get("relevant_authors", [])
        authors = [AuthorDto(**author).to_author() for author in relevant_authors]

        formset_class = AuthorFormset.use_institutions(
            fundingrequests.get_institutions_allowed_as_affiliation(for_authors=authors)
        )

        formset = cast(
            AuthorFormset,
            restore_formset(
                formset_class,
                request,
                store_data=relevant_authors,
                prefix="relevant-authors",
            ),
        )

        return formset

    def get_publication_form(self, request: HttpRequest, store: Store) -> PublicationForm:
        step_dto = store.get("publication_step")
        meta = None
        if step_dto:
            meta = UpdatePublicationMetadataCommand(**step_dto).meta

        allowed = self.get_allowed_concepts(meta)

        if PublicationForm.form_posted(request.POST):
            return PublicationForm(request.POST, allowed)
        elif meta:
            return PublicationForm.from_dto(meta, allowed)
        else:
            return PublicationForm(concepts=allowed)

    def get_allowed_concepts(self, meta: PublicationMetaDto | None) -> AllowedConcepts:
        if not meta:
            return AllowedConcepts.for_new_publication(self.publication_kind)

        publication_type = meta.publication_type.to_concept()
        subject_area = meta.subject_area.to_concept()
        return AllowedConcepts.for_existing_concepts(
            self.publication_kind,
            publication_type=publication_type,
            subject_area=subject_area,
        )

    def get_authors(self, request: HttpRequest, store: Store) -> AuthorNames:
        if request.POST.get("authors"):
            return AuthorNames.from_str(request.POST.get("authors", ""))
        elif publication_step := store.get("publication_step"):
            return AuthorNames(publication_step["other_authors"])
        else:
            return AuthorNames()

    def get_links_context(self, request: HttpRequest, store: Store) -> list[dict[str, Any]]:
        if self.has_links(request):
            return self.assemble_link_dtos(request)
        elif publication_step := store.get("publication_step"):
            links = publication_step.get("links", [])
            return [{"link": link, "errors": {}} for link in links]

        return []

    def has_links(self, request: HttpRequest) -> bool:
        return bool(request.POST.get("link_type") and request.POST.get("link_value"))

    def assemble_link_dtos(self, request: HttpRequest) -> list[dict[str, Any]]:
        forms = self.link_forms(request)
        for form in forms:
            form.full_clean()

        return [{"link": form.get_form_data(), "errors": form.errors} for form in forms]

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        authors_formset = self.get_author_formset(request, store)
        publication_form = self.get_publication_form(request, store)
        link_formset = self.link_forms(request)
        valid = self.all_valid((authors_formset, publication_form, *link_formset))
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        authors_formset = self.get_author_formset(request, store)
        publication_form = self.get_publication_form(request, store)
        link_forms = self.link_forms(request)
        self.clean_all((publication_form, *link_forms))

        store["publication_step"] = UpdatePublicationMetadataCommand(
            relevant_authors=authors_formset.to_dtos(),
            meta=publication_form.to_dto(),
            other_authors=list(AuthorNames.from_str(request.POST.get("authors", ""))),
            links=[linkform.get_form_data() for linkform in link_forms],
        ).to_post_data()
        store.save()

    def all_valid(self, forms: Iterable[FormLike]) -> bool:
        for form in forms:
            if not form.is_valid():
                return False

        return True

    def clean_all(self, forms: Iterable[FormLike]) -> None:
        for form in forms:
            form.full_clean()

    def link_forms(self, request: HttpRequest) -> Iterable[LinkForm]:
        types, values = request.POST.getlist("link_type"), request.POST.getlist("link_value")
        return [
            LinkForm({"link_type": link_type, "link_value": link_value})
            for link_type, link_value in zip(types, values)
        ]


@login_required
def parse_authors(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "fundingrequests/partials/author_textarea.html",
        {"authors": AuthorNames.from_str(request.POST.get("authors", ""))},
    )


@login_required
def add_linkrow(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "partials/linkrow.html",
        {"link_types": LinkType.objects.all()},
    )
