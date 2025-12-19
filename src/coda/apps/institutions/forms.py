from typing import Any

from django import forms
from coda.apps import widgets

from coda.apps.institutions.models import Institution, InstitutionLinkType
from coda.domain.institution.links import InvalidRor, Ror


class InstitutionForm(forms.ModelForm[Institution]):
    class Meta:
        model = Institution
        fields = ["name", "parent"]

        widgets = {"parent": widgets.SearchSelectWidget()}


class InstitutionLinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(
        choices=lambda: InstitutionLinkType.objects.values_list("id", "name")
    )
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return

        try:
            link_type = InstitutionLinkType.objects.get(id=self.cleaned_data["link_type"])
            value = self.cleaned_data["link_value"]

            if link_type.name == "ROR":
                validated_link = Ror(value)
                self.cleaned_data["link_value"] = validated_link.value()
            # Add more validators as implemented:
            # elif link_type.name == "ISNI":
            #     validated_link = Isni(value)
            #     self.cleaned_data["link_value"] = validated_link.value()
            # elif link_type.name == "Ringold":
            #     validated_link = Ringold(value)
            #     self.cleaned_data["link_value"] = validated_link.value()

        except InvalidRor as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> dict[str, Any]:
        return {
            "type_id": int(self.cleaned_data["link_type"]),
            "value": str(self.cleaned_data.get("link_value", self.data.get("link_value", ""))),
        }
