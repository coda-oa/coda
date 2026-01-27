from typing import Any

from django import forms
from coda.apps import widgets

from coda.apps.institutions.models import Institution, InstitutionLinkType
from coda.domain.institution.links import (
    InvalidIsni,
    InvalidRinggold,
    InvalidRor,
    create_link,
)


class InstitutionForm(forms.ModelForm[Institution]):
    class Meta:
        model = Institution
        fields = ["name", "parent"]

        widgets = {"parent": widgets.SearchSelectWidget()}


def _link_type_choices() -> list[tuple[str, str]]:
    return [(lt, lt) for lt in InstitutionLinkType.objects.values_list("name", flat=True)]


class InstitutionLinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(choices=_link_type_choices)
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return

        try:
            link_type_name = self.cleaned_data["link_type"]
            value = self.cleaned_data["link_value"]

            validated_link = create_link(link_type_name, value)
            self.cleaned_data["link_value"] = validated_link.value()

        except (InvalidRor, InvalidIsni, InvalidRinggold) as err:
            self.add_error("link_value", str(err))

        except ValueError as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> dict[str, Any]:
        return {
            "link_type": self.cleaned_data.get("link_type", self.data.get("link_type", "")),
            "link_value": self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        }
