from collections.abc import Mapping
from typing import Any

from django import forms

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Role
from coda.apps.authors.services import orcid_validator
from coda.apps.institutions.models import Institution


class OrcidField(forms.CharField):
    def clean(self, value: Any) -> Any:
        if not value and not self.required:
            return super().clean(value)

        return orcid_validator(value)


class AuthorForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
    orcid = OrcidField(required=False)
    affiliation = forms.ModelChoiceField(queryset=Institution.objects.all(), required=False)
    role = forms.ChoiceField(choices=((role.name, role.value) for role in Role), required=False)

    def to_dto(self) -> AuthorDto:
        data = self.cleaned_data
        return AuthorDto(
            name=data["name"],
            email=data["email"],
            orcid=data.get("orcid"),
            affiliation=self.affiliation_pk(data),
            roles=[data["role"]],
        )

    def affiliation_pk(self, data: Mapping[str, Any]) -> int | None:
        if not data.get("affiliation"):
            return None

        affiliation = data["affiliation"]
        match affiliation:
            case int() | str():
                return int(affiliation)
            case Institution():
                return affiliation.pk
            case _:
                return None
