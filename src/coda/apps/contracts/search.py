from django.db.models import Q

from coda.apps.search import ScopedAlias, SearchFieldAliases

CONTRACT_SEARCH_FIELD_ALIASES: SearchFieldAliases = {
    "name": "name",
    "esac": ScopedAlias("links__value", Q(links__type__name="ESAC")),
    "oai": ScopedAlias("links__value", Q(links__type__name="OAI")),
    "ezb": ScopedAlias("links__value", Q(links__type__name="EZB")),
}
