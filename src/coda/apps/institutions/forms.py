from typing import Any

from django import forms
from coda.apps import widgets

from coda.apps.institutions.models import Institution, InstitutionLinkType
from coda.apps.institutions.services import generate_internal_id
from coda.domain.institution.links import (
    InvalidIsni,
    InvalidRinggold,
    InvalidRor,
    create_link,
)


class InstitutionForm(forms.ModelForm[Institution]):
    class Meta:
        model = Institution
        fields = ["name", "parent", "internal_id"]

        widgets = {"parent": widgets.SearchSelectWidget()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["internal_id"].help_text = ""

    def clean(self) -> dict[str, Any] | None:
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data

        instance = self.instance
        parent: Institution | None = cleaned_data.get("parent")
        if parent is None or instance.pk is None:
            return cleaned_data

        if parent.pk == instance.pk or parent.is_descendant_of(instance):
            self.add_error(
                "parent",
                "This parent would create a cycle in the institution hierarchy. "
                "An institution cannot be its own ancestor.",
            )
        return cleaned_data

    def save(self, commit: bool = True) -> Institution:
        instance = super().save(commit=False)
        if not instance.internal_id:
            instance.internal_id = generate_internal_id()
        if commit:
            instance.save()
        return instance


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
