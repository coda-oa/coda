from django import forms

from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import Label
from coda.money import Currency


class FundingForm(forms.Form):
    estimated_cost = forms.DecimalField(max_digits=10, decimal_places=4, label="")
    estimated_cost_currency = forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency], initial=Currency.EUR.code, label=""
    )

    def to_dto(self) -> FundingDto:
        return FundingDto(
            estimated_cost=self.cleaned_data["estimated_cost"],
            estimated_cost_currency=self.cleaned_data["estimated_cost_currency"],
        )


class LabelForm(forms.ModelForm[Label]):
    class Meta:
        model = Label
        fields = "__all__"
        widgets = {"hexcolor": forms.TextInput(attrs={"type": "color"})}


class ChooseLabelForm(forms.Form):
    label = forms.ModelChoiceField(queryset=Label.objects.all(), label="")
