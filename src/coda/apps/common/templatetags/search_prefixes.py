from django import template

from coda.apps.fundingrequests.fundingrequest_query import (
    SEARCH_FIELD_ALIASES as FR_SEARCH_FIELD_ALIASES,
)
from coda.apps.invoices.views.search import (
    CONTRACT_SEARCH_FIELD_ALIASES,
    PUBLICATION_SEARCH_FIELD_ALIASES,
)

register = template.Library()


@register.simple_tag
def publication_search_prefixes() -> str:
    return ", ".join(PUBLICATION_SEARCH_FIELD_ALIASES)


@register.simple_tag
def fundingrequest_search_prefixes() -> str:
    return ", ".join(FR_SEARCH_FIELD_ALIASES)


@register.simple_tag
def contract_search_prefixes() -> str:
    return ", ".join(CONTRACT_SEARCH_FIELD_ALIASES)
