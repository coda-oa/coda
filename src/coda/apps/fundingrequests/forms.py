from typing import Any
from django import forms

from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import FundingOrganization, FundingRequest, Label
from coda.money import Currency


class CostForm(forms.Form):
    use_required_attribute = False
    estimated_cost = forms.DecimalField(max_digits=10, decimal_places=2, initial=0)
    estimated_cost_currency = forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency], initial=Currency.EUR.code, label="Currency"
    )
    payment_method = forms.ChoiceField(choices=FundingRequest.PAYMENT_METHOD_CHOICES)

    def to_dto(self) -> CostDto:
        return CostDto(
            estimated_cost=self.cleaned_data["estimated_cost"],
            estimated_cost_currency=self.cleaned_data["estimated_cost_currency"],
            payment_method=self.cleaned_data["payment_method"],
        )


class ExternalFundingForm(forms.Form):
    use_required_attribute = False
    organization = forms.ModelChoiceField(FundingOrganization.objects.all())
    project_id = forms.CharField()
    project_name = forms.CharField(required=False)

    def is_valid(self) -> bool:
        is_valid = super().is_valid()
        organization = self.cleaned_data.get("organization")

        if organization:
            return is_valid

        if not self.is_empty():
            self._add_missing_organization_error()

        return False

    def is_empty(self) -> bool:
        return not any(self.cleaned_data.values())

    def clean(self) -> dict[str, Any] | None:
        cleaned = super().clean()
        organization = self.cleaned_data.get("organization")

        if organization is None:
            self.errors.pop("organization", None)
            self.errors.pop("project_id", None)
            self.errors.pop("project_name", None)

        return cleaned

    def to_dto(self) -> ExternalFundingDto | None:
        if self.is_empty():
            return None

        return ExternalFundingDto(
            organization=self.cleaned_data["organization"].pk,
            project_id=self.cleaned_data["project_id"],
            project_name=self.cleaned_data["project_name"],
        )

    def _add_missing_organization_error(self) -> None:
        self.add_error(
            "organization",
            "Please select a funding organization to provide project information",
        )


class LabelForm(forms.ModelForm[Label]):
    class Meta:
        model = Label
        fields = "__all__"
        widgets = {"hexcolor": forms.TextInput(attrs={"type": "color"})}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField(queryset=Label.objects.all(), label="")
