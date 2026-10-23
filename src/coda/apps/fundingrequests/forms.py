import datetime
import functools
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, cast

from django import forms
from django.contrib.auth.decorators import login_required
from django.db import models
from django.forms import ModelChoiceField
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.datastructures import MultiValueDict
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
from coda.apps.institutions import repository as institution_repository
from coda.apps.invoices.models import FundingSource
from coda.apps.journals.models import Journal
from coda.apps.listfilters import (
    DateRangeField,
    ListSortOrder,
    named_model_choices,
    valid_fields,
)
from coda.apps.preferences.models import GlobalPreferences, PreloadedVocabularyProvider
from coda.apps.publications.dto import ContractYearDto
from coda.apps.publishers.models import Publisher
from coda.apps.widgets import (
    PublicationTypeRadioSelect,
    SearchSelectMultiWidget,
    SearchSelectWidget,
    SwitchInput,
)
from coda.contexts.fundingrequest.dto.commands import (
    ExternalFundingDto,
    PaymentDto,
    UpdateReviewDto,
)
from coda.domain.author import InstitutionId
from coda.domain.contract import ContractId, ContractYear
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.links import FundingOrganizationLink, create_link, link_types
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import License, OpenAccessType
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
        return not contract.is_active(timezone.now().astimezone(datetime.UTC).date())

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
            cast(
                ModelChoiceField[FundingOrganization], self.fields["organization"]
            ).queryset = organization_queryset

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
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "name": forms.TextInput(attrs={"autofocus": True}),
            "hexcolor": forms.ColorInput(),
        }
        labels: ClassVar[dict[str, str]] = {"hexcolor": "Color"}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField[Label](queryset=Label.objects.all(), label="")


class ReviewForm(forms.Form):
    ACTION_RETURN = "return"

    action = forms.ChoiceField(
        choices=[(result.value, result.value) for result in ReviewResult]
        + [(ACTION_RETURN, ACTION_RETURN)],
    )
    decided_funding_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label="Decided funding amount",
        widget=forms.TextInput(attrs={"type": "number", "min": "0", "step": "0.01"}),
    )
    decided_funding_currency = fields.currency_field(label="Currency")
    reviewer_remarks = forms.CharField(widget=forms.Textarea, required=False)

    def to_dto(self) -> UpdateReviewDto:
        result = (
            "" if self.cleaned_data["action"] == self.ACTION_RETURN else self.cleaned_data["action"]
        )
        return UpdateReviewDto(
            decided_funding_amount=self.cleaned_data["decided_funding_amount"],
            decided_funding_currency=self.cleaned_data["decided_funding_currency"],
            reviewer_remarks=self.cleaned_data["reviewer_remarks"],
            result=result,
        )


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
license_choices = [(l.value, l.value) for l in License]
publication_form_choices = [(form.value, form.value.title()) for form in fq.PublicationForm]
cost_type_choices = [(ct.value, ct.value) for ct in PublicationCostType]


def publication_type_vocabulary_choices(
    vocabularies: PreloadedVocabularyProvider | None = None,
) -> list[tuple[str, str]]:
    """The concepts the wizard's publication-type step offers — the configured
    article and monograph vocabularies (``AllowedConcepts`` reads the very same
    ``GlobalPreferences`` rows; the facet cannot know the entity kind, so it
    offers both). Blank names — the default concept row — select nothing. The
    rest of the ``PublicationAttachedConcept`` registry (subject-area concepts
    in particular) is deliberately not offered."""
    if vocabularies is None:
        vocabularies = GlobalPreferences.preloaded()
    concepts = [
        *vocabularies.get_article_publication_type_vocabulary().concepts,
        *vocabularies.get_monograph_publication_type_vocabulary().concepts,
    ]
    return list(
        {
            str(concept.id): concept.name
            for concept in sorted(concepts, key=lambda concept: concept.name)
            if concept.name
        }.items()
    )


def parse_label_ids(values: Iterable[str]) -> set[int]:
    """Parse label ids from query values, ignoring non-integer values."""
    ids = set()
    for value in values:
        try:
            ids.add(int(value))
        except ValueError:
            continue
    return ids


_FACET_CHOICE_LIMIT = 100


def _selected_pks(selected: Iterable[str]) -> list[int]:
    """The numeric selection; runs during form construction, before field
    validation — garbage in the URL (a crafted ``?journal=²`` or ``['abc']``)
    must narrow nothing, not crash the view; the field reports the error."""
    pks = []
    for value in selected:
        try:
            pks.append(int(value))
        except (TypeError, ValueError):
            continue
    return pks


def facet_choices(
    model: type[Journal] | type[Publisher], label_field: str, selected: Iterable[str], query: str
) -> list[tuple[Any, str]]:
    """The rendered choices for a registry-scale facet: the first
    ``_FACET_CHOICE_LIMIT`` matches of ``query`` in alphabetical order, plus
    every already-selected row (which may fall outside that cap). Enumerating
    the whole registry instead blows up the rail on real data volumes.
    """
    matches = (
        model.objects.filter(**{f"{label_field}__icontains": query})
        if query
        else model.objects.all()
    )
    choices = [
        (obj.pk, str(getattr(obj, label_field)))
        for obj in matches.order_by(label_field)[:_FACET_CHOICE_LIMIT]
    ]
    shown = {pk for pk, _ in choices}
    selected_pks = _selected_pks(selected)
    missing = model.objects.filter(pk__in=selected_pks).exclude(pk__in=shown)
    choices += [(obj.pk, str(getattr(obj, label_field))) for obj in missing]
    return choices


class FundingRequestListFilterForm(forms.Form):
    """Validation and query mapping for the funding-request filter controls.

    A value that fails validation lands in ``form.errors`` and its criterion is
    dropped; the raw param stays in the URL so its chip keeps it removable.
    The form resolves the ``labels``/``exclude_labels`` params against the
    ``labels`` set: ids outside it filter nothing and get no chip, so the URL
    cannot select a label the filters do not offer.
    """

    def __init__(
        self,
        *args: Any,
        contracts: Iterable[Contract] = (),
        labels: Iterable[Label] = (),
        vocabularies: PreloadedVocabularyProvider | None = None,
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
        self.selected_label_ids: set[int] = set()
        self.excluded_label_ids: set[int] = set()
        if data is not None:
            selectable = {label.pk for label in label_options}
            self.selected_label_ids = parse_label_ids(data.getlist("labels")) & selectable
            self.excluded_label_ids = parse_label_ids(data.getlist("exclude_labels")) & selectable

        if vocabularies is not None:
            # These fields' choices are callables; left to their defaults each
            # access re-fetches the preferences singleton and its vocabulary
            # batches. A caller that builds the form — the statistics page —
            # passes one provider shared with the drill-down tables instead.
            subject_field = cast(forms.TypedMultipleChoiceField, self.fields["subject_area"])
            subject_field.choices = lambda: [
                (str(concept.id), concept.name)
                for concept in vocabularies.get_subject_classification_vocabulary().concepts
            ]
            concept_field = cast(
                forms.TypedMultipleChoiceField, self.fields["publication_type_concept"]
            )
            concept_field.choices = lambda: publication_type_vocabulary_choices(vocabularies)

        data = (
            self.data
            if isinstance(self.data, MultiValueDict)
            else MultiValueDict({k: [v] for k, v in self.data.items()})
        )
        for field_name, (model, label_field) in (
            ("journal", (Journal, "title")),
            ("publisher", (Publisher, "name")),
        ):
            query = data.get(f"{field_name}_q", "").strip()
            widget = cast(SearchSelectMultiWidget, self.fields[field_name].widget)
            widget.remote_search = True
            widget.remote_query = query
            field = cast(forms.TypedMultipleChoiceField, self.fields[field_name])
            # Lazy like the class-level choice lambdas it replaces: form
            # instantiation must not hit the database.
            field.choices = functools.partial(
                facet_choices, model, label_field, data.getlist(field_name), query
            )

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
    institution = forms.TypedMultipleChoiceField(
        coerce=lambda value: InstitutionId(int(value)),
        choices=lambda: [(inst.pk, inst.name) for inst in institution_repository.non_virtuals()],
        required=False,
        label="Institution",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_institution",
                "class": "w-100",
                "placeholder": "Select institutions",
            }
        ),
    )
    publisher = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=lambda: [(pub.pk, pub.name) for pub in Publisher.objects.order_by("name")],
        required=False,
        label="Publisher",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_publisher",
                "class": "w-100",
                "placeholder": "Select publishers",
            }
        ),
    )
    journal = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=lambda: [(j.pk, j.title) for j in Journal.objects.order_by("title")],
        required=False,
        label="Journal",
        widget=SearchSelectMultiWidget(
            attrs={"id": "id_journal", "class": "w-100", "placeholder": "Select journals"}
        ),
    )
    funder = forms.TypedMultipleChoiceField(
        coerce=int,
        choices=lambda: [(f.pk, f.name) for f in FundingOrganization.objects.order_by("name")],
        required=False,
        label="Funder",
        widget=SearchSelectMultiWidget(
            attrs={"id": "id_funder", "class": "w-100", "placeholder": "Select funders"}
        ),
    )
    subject_area = forms.TypedMultipleChoiceField(
        coerce=uuid.UUID,
        choices=lambda: [
            (str(concept.id), concept.name)
            for concept in GlobalPreferences.get_subject_classification_vocabulary().concepts
        ],
        required=False,
        label="Subject area",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_subject_area",
                "class": "w-100",
                "placeholder": "Select subject areas",
            }
        ),
    )
    publication_type_concept = forms.TypedMultipleChoiceField(
        coerce=uuid.UUID,
        choices=publication_type_vocabulary_choices,
        required=False,
        label="Publication type",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_publication_type_concept",
                "class": "w-100",
                "placeholder": "Select publication types",
            }
        ),
    )
    license = forms.TypedMultipleChoiceField(
        coerce=License,
        choices=license_choices,
        required=False,
        label="License",
        widget=forms.SelectMultiple(attrs={"id": "id_license", "class": "w-100"}),
    )
    publication_form = forms.TypedChoiceField(
        coerce=fq.PublicationForm,
        # A non-multiple <select> always displays its first option — without a
        # blank choice every htmx submit would silently add publication_form=
        # article and narrow the whole list (pinned in tests/fundingrequests).
        choices=[("", "-------"), *publication_form_choices],
        required=False,
        label="Publication form",
        widget=forms.Select(attrs={"id": "id_publication_form", "class": "w-100"}),
    )
    cost_type = forms.TypedMultipleChoiceField(
        coerce=PublicationCostType,
        choices=cost_type_choices,
        required=False,
        label="Cost type",
        widget=forms.SelectMultiple(attrs={"id": "id_cost_type", "class": "w-100"}),
    )
    funding_source = forms.TypedMultipleChoiceField(
        coerce=lambda value: FundingSourceId(int(value)),
        choices=lambda: [
            (source.pk, source.name) for source in FundingSource.objects.order_by("name")
        ],
        required=False,
        label="Funding source",
        widget=SearchSelectMultiWidget(
            attrs={
                "id": "id_funding_source",
                "class": "w-100",
                "placeholder": "Select funding sources",
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
        *,
        date_override: tuple[datetime.date, datetime.date] | None = None,
    ) -> tuple[list[fq.FundingRequestSearchCriteria], ListSortOrder]:
        """Translate validated filter fields into criteria and their sort order.

        ``date_override`` replaces the form's date range — the comparison
        toggle fetches the previous period through the same filters.
        """
        cleaned = valid_fields(self)
        if date_override is not None:
            start, end = date_override
            date_range = fq.DateRange(start=start, end=end)
        else:
            date_range = cleaned.get("date_range")
        params = fq.FundingRequestSearchParams(
            date_range=date_range,
            review_results=cleaned.get("processing_status", []),
            payment_statuses=cleaned.get("payment_status", []),
            labels=sorted(self.selected_label_ids),
            exclude_labels=sorted(self.excluded_label_ids),
            payment_methods=cleaned.get("payment_methods", []),
            open_access_types=cleaned.get("open_access_type", []),
            publication_states=cleaned.get("publication_states", []),
            entity_type=cleaned.get("publication_type") or fq.PublicationEntityType.All,
            search_term=cleaned.get("search_term", ""),
            contract_id=cleaned.get("contract_name"),
            contract_year=cleaned.get("contract_year"),
            institutions=cleaned.get("institution", []),
            publishers=cleaned.get("publisher", []),
            journals=cleaned.get("journal", []),
            funders=cleaned.get("funder", []),
            subject_areas=cleaned.get("subject_area", []),
            publication_type_concepts=cleaned.get("publication_type_concept", []),
            licenses=cleaned.get("license", []),
            publication_form=cleaned.get("publication_form"),
            cost_types=cleaned.get("cost_type", []),
            funding_sources=cleaned.get("funding_source", []),
            show_invalid_contract_years=bool(cleaned.get("invalid_contract_years")),
        )
        return fq.build_criteria(params), ListSortOrder.parse_or_default(cleaned.get("sort_by"))
