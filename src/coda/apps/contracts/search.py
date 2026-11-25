from collections.abc import Callable

from django.db.models import Exists, OuterRef, Q

from coda.apps.contracts.models import ContractLink
from coda.apps.search import ScopedAlias, SearchFieldAliases


def _link_term_query(link_type: str) -> Callable[[str], Q]:
    def term_query(value: str) -> Q:
        return Q(
            Exists(
                ContractLink.objects.filter(
                    contract_id=OuterRef("pk"),
                    type__name=link_type,
                    value__icontains=value,
                )
            )
        )

    return term_query


CONTRACT_SEARCH_FIELD_ALIASES: SearchFieldAliases = {
    "name": "name",
    "esac": ScopedAlias("links__value", Q(), term_query=_link_term_query("ESAC")),
    "oai": ScopedAlias("links__value", Q(), term_query=_link_term_query("OAI")),
    "ezb": ScopedAlias("links__value", Q(), term_query=_link_term_query("EZB")),
}
