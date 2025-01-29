from typing import Any

from django import forms

from coda.apps import fields
from coda.apps.contracts.models import Contract
from coda.apps.contracts.services import as_domain_object
from coda.apps.formbase import CodaFormBase
from coda.apps.fundingrequests.dto import ExternalFundingDto, PaymentDto
from coda.apps.fundingrequests.models import FundingOrganization, FundingRequest, Label
from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.apps.publications.dto import ContractYearDto
from coda.contract import ContractYear


class ExtraContactForm(CodaFormBase):
    name = forms.CharField()
    email = forms.EmailField()

    def to_dto(self) -> dict[str, Any]:
        return self.cleaned_data


class ContractForm(CodaFormBase):
    contract = forms.ModelChoiceField[Contract](queryset=Contract.objects.all())
    year = forms.IntegerField()

    def contract_year(self) -> ContractYear:
        return as_domain_object(self.cleaned_data["contract"]).in_year(self.cleaned_data["year"])

    def to_dto(self) -> ContractYearDto:
        return ContractYearDto(
            contract=self.cleaned_data["contract"].pk, year=self.cleaned_data["year"]
        )

    def is_valid(self) -> bool:
        is_valid = super().is_valid()

        try:
            _ = self.contract_year()
        except (ValueError, KeyError) as e:
            self.add_error("year", str(e))
            return False

        return is_valid


class ContractFormset(HtmxDynamicFormset[ContractForm]):
    name = "fundingrequests:contract_formset"
    form_class = ContractForm
    min_forms = 0

    def contract_years(self) -> list[ContractYear]:
        return [form.contract_year() for form in self.forms]

    def to_dto_list(self) -> list[ContractYearDto]:
        return [form.to_dto() for form in self.forms]


class PaymentForm(CodaFormBase):
    use_required_attribute = False
    amount = forms.DecimalField(max_digits=10, decimal_places=2, initial=0, label="Estimated cost")
    currency = fields.currency_field(label="Currency")
    method = forms.ChoiceField(
        choices=FundingRequest.PAYMENT_METHOD_CHOICES, label="Payment method"
    )

    def to_dto(self) -> PaymentDto:
        return PaymentDto(
            amount=float(self.cleaned_data["amount"]),
            currency=self.cleaned_data["currency"],
            method=self.cleaned_data["method"],
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

    def is_empty(self) -> bool:
        return all(form.is_empty() for form in self.forms)

    def to_dto_list(self) -> list[ExternalFundingDto]:
        _dtos = [form.to_dto() for form in self.forms]
        return [dto for dto in _dtos if dto is not None]


class LabelForm(forms.ModelForm[Label]):
    class Meta:
        model = Label
        fields = "__all__"
        widgets = {"hexcolor": forms.TextInput(attrs={"type": "color"})}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField[Label](queryset=Label.objects.all(), label="")


class ReviewForm(forms.Form):
    funding_sum = forms.DecimalField(
        max_digits=10, decimal_places=2, initial=0, label="Funding sum"
    )
    funding_currency = fields.currency_field(label="Currency")
    reviewer_comments = forms.CharField(widget=forms.Textarea, required=False)
