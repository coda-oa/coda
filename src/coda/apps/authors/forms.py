from collections.abc import Iterable, Mapping
from functools import cache
from typing import Any

from django import forms
from django.forms.utils import ErrorList

from coda.apps import widgets
from coda.apps.authors.dto import AuthorDto
from coda.apps.formbase import CodaFormBase
from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.apps.institutions import repository
from coda.apps.institutions.models import Institution
from coda.author import Author, InstitutionId, Role
from coda.orcid import Orcid
from coda.publication import Authors
from coda.validation import as_validator


class OrcidField(forms.CharField):
    @as_validator
    def clean(self, value: Any) -> Any:
        if not value and not self.required:
            return super().clean(value)

        return Orcid(value)


class AuthorForm(CodaFormBase):
    use_required_attribute = False

    name = forms.CharField()
    email = forms.EmailField()
    orcid = OrcidField(required=False)
    affiliation = forms.ChoiceField(
        choices=lambda: (
            (None, "-------"),
            *((inst.pk, inst.name) for inst in repository.non_virtuals()),
        ),
        required=False,
        widget=widgets.SearchSelectWidget,
    )
    role = forms.ChoiceField(
        choices=((role.name, role.value) for role in Role),
        required=False,
    )

    def to_dto(self) -> AuthorDto:
        data = dict(self.cleaned_data)
        data["affiliation"] = get_affiliation_pk(data)
        return AuthorDto(**data)

    def to_author(self) -> Author:
        return self.to_dto().to_author()


class AuthorFormset(HtmxDynamicFormset[AuthorForm]):
    min_forms = 1
    name = "authors:author_formset_view"
    form_class = AuthorForm
    table_classes = "inline-table-form"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.errors = ErrorList()

    @classmethod
    def use_institutions(cls, institutions: Iterable[Institution]) -> "type[AuthorFormset]":
        class AuthorFormWithInstitutions(AuthorForm):
            affiliation = forms.ChoiceField(
                choices=((inst.pk, inst.name) for inst in institutions),
                required=False,
                widget=widgets.SearchSelectWidget,
            )

        class AuthorFormsetWithInstitutions(AuthorFormset):
            form_class = AuthorFormWithInstitutions

        return AuthorFormsetWithInstitutions

    @cache
    def to_dtos(self) -> list[AuthorDto]:
        return [form.to_dto() for form in self.forms]

    @cache
    def is_valid(self) -> bool:
        if not super().is_valid():
            return False

        authors = list(map(AuthorDto.to_author, self.to_dtos()))

        try:
            Authors(authors)
        except ValueError:
            submitter_indices = [
                index for index, author in enumerate(authors) if author.is_submitter()
            ]

            for index in submitter_indices:
                self.forms[index].add_error(
                    "role", "Publication can only have one submitting author"
                )

            return False

        return True


def get_affiliation_pk(data: Mapping[str, Any]) -> InstitutionId | None:
    if not data.get("affiliation"):
        return None

    affiliation = data["affiliation"]
    match affiliation:
        case int() | str():
            return InstitutionId(int(affiliation))
        case Institution():
            return InstitutionId(affiliation.pk)
        case _:
            return None
