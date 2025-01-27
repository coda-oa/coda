from collections.abc import Mapping
from typing import Any

from django import forms

from coda.apps import widgets
from coda.apps.authors.dto import AuthorDto
from coda.apps.formbase import CodaFormBase
from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.apps.institutions import repository
from coda.apps.institutions.models import Institution
from coda.author import Author, InstitutionId, Role
from coda.orcid import Orcid
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
