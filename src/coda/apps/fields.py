from django import forms

from coda.apps import widgets
from coda.domain.money import Currency


def currency_field(label: str | None = None) -> forms.ChoiceField:
    return forms.ChoiceField(
        choices=[(c.code, c.code) for c in Currency],
        initial=Currency.EUR.code,
        widget=widgets.SearchSelectWidget,
        label=label,
    )
