from django import forms

from coda.money import Currency


class FundingRequestForm(forms.Form):
    estimated_cost = forms.DecimalField(max_digits=10, decimal_places=4, label="")
    estimated_cost_currency = forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency], initial=Currency.EUR.code, label=""
    )
