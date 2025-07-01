from django import forms

from coda.apps.htmx_components.forms import HtmxDynamicFormset
from coda.domain.contract import Contract, PublicationBilling
from coda.domain.date import DateRange
from coda.domain.string import NonEmptyStr


class ContractForm(forms.Form):
    use_required_attribute = False
    name = forms.CharField(required=True)
    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))
    publication_billing = forms.ChoiceField(
        choices=[(billing_type.value, billing_type.value) for billing_type in PublicationBilling],
    )

    @classmethod
    def from_contract(cls, contract: Contract) -> "ContractForm":
        return cls(
            {
                "name": contract.name,
                "start_date": contract.period.start,
                "end_date": contract.period.end,
                "publication_billing": contract.publication_billing.value,
            }
        )

    def get_name(self) -> NonEmptyStr:
        return NonEmptyStr(self.cleaned_data["name"])

    def get_period(self) -> DateRange:
        return DateRange(start=self.cleaned_data["start_date"], end=self.cleaned_data["end_date"])

    def get_billing(self) -> PublicationBilling:
        return PublicationBilling(self.cleaned_data["publication_billing"])


class EntityForm(forms.Form):
    use_required_attribute = False
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"readonly": True}),
    )
    entity_id = forms.IntegerField(widget=forms.HiddenInput())


class EntityFormset(HtmxDynamicFormset[EntityForm]):
    form_class = EntityForm
    name = "contracts:entity-formset"
    add_button = False
    min_forms = 0

    def entity_ids(self) -> list[int]:
        return [cleaned_data["entity_id"] for cleaned_data in self.data]
