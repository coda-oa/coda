from django import forms
from coda.apps.fundingrequests.models import FundingDto

from coda.money import Currency


class FundingForm(forms.Form):
    estimated_cost = forms.DecimalField(max_digits=10, decimal_places=4, label="")
    estimated_cost_currency = forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency], initial=Currency.EUR.code, label=""
    )

    def to_dto(self) -> FundingDto:
        return {
            "estimated_cost": self.cleaned_data["estimated_cost"],
            "estimated_cost_currency": self.cleaned_data["estimated_cost_currency"],
        }
