from typing import Any

from django import forms
from django.utils.datastructures import MultiValueDict

from coda.apps import fields
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import FundingOrganization, FundingRequest, Label
from coda.apps.htmx_components.forms import HtmxDynamicFormset


class ContractForm(forms.Form):
    contract = forms.ModelChoiceField[Contract](queryset=Contract.objects.all())


class ContractFormset(HtmxDynamicFormset[ContractForm]):
    name = "fundingrequests:contract_formset"
    form_class = ContractForm
    min_forms = 0

    table_classes = "article__table"


class CostForm(forms.Form):
    use_required_attribute = False
    estimated_cost = forms.DecimalField(max_digits=10, decimal_places=2, initial=0)
    estimated_cost_currency = fields.currency_field()
    payment_method = forms.ChoiceField(choices=FundingRequest.PAYMENT_METHOD_CHOICES)

    def to_dto(self) -> CostDto:
        return CostDto(
            estimated_cost=float(self.cleaned_data["estimated_cost"]),
            estimated_cost_currency=self.cleaned_data["estimated_cost_currency"],
            payment_method=self.cleaned_data["payment_method"],
        )


class ExternalFundingForm(forms.Form):
    use_required_attribute = False
    organization = forms.ModelChoiceField[FundingOrganization](FundingOrganization.objects.all())
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


class ExternalFundingFormset(HtmxDynamicFormset[ExternalFundingForm]):
    name: str = "fundingrequests:external_funding_formset"
    form_class = ExternalFundingForm

    @classmethod
    def from_data(cls, data: list[dict[str, Any]]) -> "ExternalFundingFormset":
        total_forms = len(data)
        form_data: dict[str, Any] = {"total_forms": [total_forms]}
        for i, d in enumerate(data, start=1):
            form_data[f"form-{i}-organization"] = [d["organization"]]
            form_data[f"form-{i}-project_id"] = [d["project_id"]]
            form_data[f"form-{i}-project_name"] = [d.get("project_name", "")]

        return cls(MultiValueDict(form_data))

    def is_empty(self) -> bool:
        return all(form.is_empty() for form in self.forms)

    def to_dto(self) -> list[ExternalFundingDto]:
        _dtos = [form.to_dto() for form in self.forms]
        return [dto for dto in _dtos if dto is not None]


class LabelForm(forms.ModelForm[Label]):
    class Meta:
        model = Label
        fields = "__all__"
        widgets = {"hexcolor": forms.TextInput(attrs={"type": "color"})}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField[Label](queryset=Label.objects.all(), label="")
