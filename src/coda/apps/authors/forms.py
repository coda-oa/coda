from collections.abc import Mapping
from typing import Any, cast

from django import forms

from coda.apps.authors.dto import AuthorDto, parse_author
from coda.apps.formbase import CodaFormBase
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
    affiliation = forms.ModelChoiceField(queryset=Institution.objects.all(), required=False)
    roles = forms.MultipleChoiceField(
        choices=((role.name, role.value) for role in Role),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    def to_dto(self) -> AuthorDto:
        data = dict(self.cleaned_data)
        data["affiliation"] = self.affiliation_pk(data)
        return cast(AuthorDto, data)

    def to_author(self) -> Author:
        return parse_author(self.to_dto(), id=None)

    def affiliation_pk(self, data: Mapping[str, Any]) -> InstitutionId | None:
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
