import datetime
from collections.abc import Iterable, Mapping
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
from coda.apps.contracts.models import Contract
from coda.apps.formbase import CodaFormBase
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingRequest,
    Label,
)
from coda.apps.fundingrequests.views.wizard.formrestore import restore_formset
from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.apps.listfilters import (
    DateRangeField,
    ListSortOrder,
    named_model_choices,
    valid_fields,
)
from coda.apps.publications.dto import ContractYearDto
from coda.apps.widgets import (
    PublicationTypeRadioSelect,
    SearchSelectMultiWidget,
    SearchSelectWidget,
    SwitchInput,
)
from coda.contexts.fundingrequest.dto.commands import ExternalFundingDto, PaymentDto
from coda.domain.contract import ContractId, ContractYear
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.links import FundingOrganizationLink, create_link, link_types
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from coda.domain.publication.publication import UnpublishedState


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
            amount=self.cleaned_data["amount"],
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
    link_type = forms.ChoiceField(choices=[(t, t) for t in link_types()])
    link_value = forms.CharField()

    def full_clean(self) -> None:
        super().full_clean()
        self._link_object = None
        if not self.cleaned_data.get("link_type") or not self.cleaned_data.get("link_value"):
            return
        try:
            self._link_object = create_link(
                self.cleaned_data["link_type"], self.cleaned_data["link_value"]
            )
            self.cleaned_data["link_value"] = self._link_object.value()
        except ValueError as err:
            self.add_error("link_value", str(err))

    def link_object(self) -> FundingOrganizationLink | None:
        """Return the validated domain Link, or None if not yet cleaned or invalid."""
        return getattr(self, "_link_object", None)

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


payment_status_choices = [
    (status.value, status.value.replace("_", " ").title()) for status in fq.PaymentStatus
]

publication_state_choices = [
    ("Published", "Published"),
    *((state.name, state.value) for state in UnpublishedState),
]
processing_status_choices = [(result.value, result.value) for result in ReviewResult]
payment_method_choices = [(method.value, method.value) for method in PaymentMethod]
open_access_type_choices = [
    (access_type.value, access_type.value) for access_type in OpenAccessType
]
publication_type_choices = [
    (entity.value, entity.value.title()) for entity in fq.PublicationEntityType
]


def parse_label_ids(values: Iterable[str]) -> set[int]:
    """Parse label ids from query values, ignoring non-integer values."""
    ids = set()
    for value in values:
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return ids


class FundingRequestListFilterForm(forms.Form):
    """Validation and query mapping for the funding-request filter controls.

    A value that fails validation lands in ``form.errors`` and its criterion is
    dropped; the raw param stays in the URL so its chip keeps it removable.
    """

    def __init__(
        self,
        *args: Any,
        contracts: Iterable[Contract] = (),
        labels: Iterable[Label] = (),
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("label_suffix", "")
        data = args[0] if args else kwargs.get("data")
        if data is not None and not data.get("publication_type"):
            data = data.copy()
            data["publication_type"] = fq.PublicationEntityType.All.value
            if args:
                args = (data, *args[1:])
            else:
                kwargs["data"] = data
        super().__init__(*args, **kwargs)

        cast(SearchSelectWidget, self.fields["contract_name"].widget).choices = named_model_choices(
            contracts
        )
        label_widget = cast(SearchSelectMultiWidget, self.fields["exclude_labels"].widget)
        label_options = list(labels)
        label_widget.choices = [(label.pk, label.name) for label in label_options]
        label_widget.option_attrs = {
            str(label.pk): {"data-color": label.hexcolor} for label in label_options
        }

    search_term = forms.CharField(required=False)
    processing_status = forms.TypedMultipleChoiceField(
        coerce=ReviewResult,
        choices=processing_status_choices,
        required=False,
        label="Processing Status",
        widget=SearchSelectMultiWidget(
            attrs={"id": "processing_status", "class": "w-100", "placeholder": "Select statuses"}
        ),
    )
    payment_status = forms.TypedMultipleChoiceField(
        coerce=fq.PaymentStatus,
        choices=payment_status_choices,
        required=False,
        label="Payment status",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_payment_status",
                "class": "w-100",
                "placeholder": "Select payment statuses",
            }
        ),
    )
    payment_methods = forms.TypedMultipleChoiceField(
        coerce=PaymentMethod,
        choices=payment_method_choices,
        required=False,
        label="Payment Method",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "payment_methods",
                "class": "w-100",
                "placeholder": "Select payment methods",
            }
        ),
    )
    open_access_type = forms.TypedMultipleChoiceField(
        coerce=OpenAccessType,
        choices=open_access_type_choices,
        required=False,
        label="Open Access Type",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "open_access_type",
                "class": "w-100",
                "placeholder": "Select open access types",
            }
        ),
    )
    publication_type = forms.TypedChoiceField(
        coerce=fq.PublicationEntityType,
        choices=publication_type_choices,
        required=False,
        initial=fq.PublicationEntityType.All.value,
        widget=PublicationTypeRadioSelect(),
    )
    publication_states = forms.Field(
        required=False,
        label="Publication State",
        widget=SearchSelectMultiWidget(
            attrs={"id": "id_publication_states", "class": "w-100"},
            choices=publication_state_choices,
        ),
    )
    contract_name = forms.IntegerField(
        required=False,
        label="Contract",
        widget=SearchSelectWidget(attrs={"id": "contract_name", "class": "w-100"}),
    )
    contract_year = forms.IntegerField(
        required=False,
        label="Contract Year",
        widget=forms.NumberInput(attrs={"id": "contract_year", "step": "1"}),
    )
    invalid_contract_years = forms.BooleanField(
        required=False,
        label="Invalid contract years only",
        widget=SwitchInput(attrs={"id": "invalid_contract_years", "role": "switch"}),
    )
    date_range = DateRangeField(
        input_names=("start_date", "end_date"),
        input_ids=("id_start_date", "id_end_date"),
    )
    labels = forms.Field(required=False, widget=forms.MultipleHiddenInput)
    exclude_labels = forms.Field(
        required=False,
        label="Exclude labels",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "exclude_labels",
                "class": "w-100",
                "placeholder": "Select labels to exclude",
            }
        ),
    )
    sort_by = forms.ChoiceField(
        choices=ListSortOrder.choices(),
        required=False,
        widget=forms.Select(attrs={"id": "sort_by", "class": "filter-sort"}),
    )

    def search_criteria(
        self,
    ) -> tuple[list[fq.FundingRequestSearchCriteria], ListSortOrder]:
        """Translate validated filter fields into criteria and their sort order."""
        cleaned = valid_fields(self)
        params = fq.FundingRequestSearchParams(
            date_range=cleaned.get("date_range"),
            review_results=cleaned.get("processing_status", []),
            payment_statuses=cleaned.get("payment_status", []),
            labels=sorted(parse_label_ids(cleaned.get("labels", []))),
            exclude_labels=sorted(parse_label_ids(cleaned.get("exclude_labels", []))),
            payment_methods=cleaned.get("payment_methods", []),
            open_access_types=cleaned.get("open_access_type", []),
            publication_states=cleaned.get("publication_states", []),
            entity_type=cleaned.get("publication_type") or fq.PublicationEntityType.All,
            search_term=cleaned.get("search_term", ""),
            contract_id=cleaned.get("contract_name"),
            contract_year=cleaned.get("contract_year"),
            show_invalid_contract_years=bool(cleaned.get("invalid_contract_years")),
        )
        return fq.build_criteria(params), ListSortOrder.parse_or_default(cleaned.get("sort_by"))
