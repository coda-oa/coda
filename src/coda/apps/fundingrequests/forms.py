import datetime
from collections.abc import Mapping
from typing import Any, cast

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import models
from django.forms import ModelChoiceField
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from coda.apps import fields
from coda.apps.contracts import repository
from coda.apps.formbase import CodaFormBase
from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLinkType,
    FundingRequest,
    Label,
)
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.apps.publications.dto import ContractYearDto
from coda.apps.widgets import SearchSelectWidget
from coda.contexts.fundingrequest.dto.commands import ExternalFundingDto, PaymentDto
from coda.domain.contract import ContractId, ContractYear
from coda.domain.fundingrequest.links import create_link


class ExtraContactForm(CodaFormBase):
    use_required_attribute = False

    name = forms.CharField()
    email = forms.EmailField()

    def is_valid(self) -> bool:
        return super().is_valid() or not self.has_changed()

    def to_dto(self) -> dict[str, Any]:
        return self.cleaned_data


class ContractForm(CodaFormBase):
    contract = forms.ChoiceField(
        choices=lambda: (
            (contract.id, contract.name) for contract in repository.get_active_contracts()
        )
    )
    year = forms.IntegerField()

    def inactive_contract_selected(self) -> bool:
        prefix = f"{self.prefix}-" if self.prefix else ""
        if not self.data.get(f"{prefix}contract"):
            return False

        contract_id = int(self.data[f"{prefix}contract"])
        contract = repository.get_by_id(ContractId(contract_id))
        return not contract.is_active(datetime.date.today())

    def include_inactive_contracts(self) -> None:
        self.fields["contract"].widget.choices = (
            (contract.id, contract.name) for contract in repository.all()
        )

    def contract_year(self) -> ContractYear:
        contract = repository.get_by_id(ContractId(self.cleaned_data["contract"]))
        return contract.in_year(self.cleaned_data["year"])

    def to_dto(self) -> ContractYearDto:
        return ContractYearDto(
            contract=self.cleaned_data["contract"], year=self.cleaned_data["year"]
        )

    def is_valid(self) -> bool:
        is_valid = super().is_valid()

        try:
            _ = self.contract_year()
        except (ValueError, KeyError) as e:
            self.add_error("year", str(e))
            return False

        return is_valid


class ContractFormWithInactive(ContractForm):
    contract = forms.ChoiceField(
        choices=lambda: ((contract.id, contract.name) for contract in repository.all())
    )


class ContractFormset(HtmxDynamicFormset[ContractForm]):
    name = "fundingrequests:contract_formset"
    form_class = ContractForm
    min_forms = 0

    @staticmethod
    def prerender_forms(
        forms: list[ContractForm], mapping: Mapping[str, Any] | None = None
    ) -> list[ContractForm]:
        if mapping and ContractFormset.use_inactive_contract_forms(forms, mapping):
            return [ContractFormWithInactive(form.data, prefix=form.prefix) for form in forms]
        return forms

    @staticmethod
    def use_inactive_contract_forms(forms: list[ContractForm], mapping: Mapping[str, Any]) -> bool:
        inactive_contracts_selected = any(form.inactive_contract_selected() for form in forms)
        include_inactive_checked = "include_inactive" in mapping
        use_inactive_contract_forms = inactive_contracts_selected or include_inactive_checked
        return use_inactive_contract_forms

    def any_inactive_contracts_selected(self) -> bool:
        return any(form.inactive_contract_selected() for form in self.forms)

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
    external_costsplitting = forms.BooleanField(
        required=False,
        initial=False,
        label="External cost splitting",
    )

    def to_dto(self) -> PaymentDto:
        return PaymentDto(
            amount=float(self.cleaned_data["amount"]),
            currency=self.cleaned_data["currency"],
            method=self.cleaned_data["method"],
            external_costsplitting=self.cleaned_data["external_costsplitting"],
        )


class ExternalFundingForm(forms.Form):
    use_required_attribute = False
    organization = forms.ModelChoiceField[FundingOrganization](
        queryset=FundingOrganization.objects.all(), widget=SearchSelectWidget()
    )
    project_id = forms.CharField()
    project_name = forms.CharField(required=False)

    def __init__(
        self,
        *args: Any,
        organization_queryset: models.QuerySet[FundingOrganization] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if organization_queryset is not None:
            cast(ModelChoiceField[FundingOrganization], self.fields["organization"]).queryset = (
                organization_queryset
            )

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

    @staticmethod
    def prerender_forms(
        forms: list[ExternalFundingForm], data: Mapping[str, Any] | None = None
    ) -> list[ExternalFundingForm]:
        if data is not None:
            org_pks = _extract_org_pks_from_forms(forms)
            if org_pks:
                archived_pks = set(
                    FundingOrganization.all_objects.filter(
                        pk__in=org_pks, archived_at__isnull=False
                    ).values_list("pk", flat=True)
                )
                if archived_pks:
                    custom_qs = (
                        FundingOrganization.objects.all()
                        | FundingOrganization.all_objects.filter(pk__in=archived_pks)
                    )
                    for form in forms:
                        cast(
                            ModelChoiceField[FundingOrganization], form.fields["organization"]
                        ).queryset = custom_qs
        return forms

    def is_empty(self) -> bool:
        return all(form.is_empty() for form in self.forms)

    def to_dto_list(self) -> list[ExternalFundingDto]:
        _dtos = [form.to_dto() for form in self.forms]
        return [dto for dto in _dtos if dto is not None]


def _extract_org_pks_from_forms(forms: list[ExternalFundingForm]) -> set[int]:
    org_pks: set[int] = set()
    for form in forms:
        org_key = form.add_prefix("organization")
        org_value = form.data.get(org_key)
        if isinstance(org_value, (int, str)) and org_value != "":
            org_pks.add(int(org_value))
    return org_pks


class LabelForm(forms.ModelForm[Label]):
    class Meta:
        model = Label
        fields = "__all__"
        widgets = {"hexcolor": forms.TextInput(attrs={"type": "color"})}
        labels = {"hexcolor": "Color"}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField[Label](queryset=Label.objects.all(), label="")


class ReviewForm(forms.Form):
    funding_sum = forms.DecimalField(
        max_digits=10, decimal_places=2, initial=0, label="Funding sum"
    )
    funding_currency = fields.currency_field(label="Currency")
    reviewer_comments = forms.CharField(widget=forms.Textarea, required=False)


class FundingOrganizationLinkForm(forms.Form):
    use_required_attribute = False
    link_type = forms.ChoiceField(
        choices=lambda: list(FundingOrganizationLinkType.objects.values_list("name", "name").all())
    )
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return
        try:
            validated = create_link(self.cleaned_data["link_type"], self.cleaned_data["link_value"])
            self.cleaned_data["link_value"] = validated.value()
        except ValueError as err:
            self.add_error("link_value", str(err))

    def get_form_data(self) -> dict[str, Any]:
        return {
            "link_type": self.cleaned_data.get("link_type", self.data.get("link_type", "")),
            "link_value": self.cleaned_data.get("link_value", self.data.get("link_value", "")),
        }


@login_required
@require_POST
def include_inactive_contracts(request: HttpRequest) -> HttpResponse:
    include_inactive = "include_inactive" in request.POST

    contract_dtos = [
        ContractYearDto(**c).to_post_data() for c in request.session.get("contracts", [])
    ]
    contract_formset = cast(
        ContractFormset,
        restore_formset(ContractFormset, request, store_data=contract_dtos, prefix="contracts"),
    )

    return render(
        request,
        "fundingrequests/forms/filtered_contract_formset.html",
        {
            "include_inactive": include_inactive,
            "contract_formset": contract_formset,
        },
    )
