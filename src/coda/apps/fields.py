from django import forms

from coda.apps import widgets
from coda.domain.money import Currency


def currency_field(label: str | None = None) -> forms.ChoiceField:
    return forms.ChoiceField(
        choices=Currency.choices(),
        initial=Currency.EUR.code,
        widget=widgets.SearchSelectWidget,
        label=label,
    )
