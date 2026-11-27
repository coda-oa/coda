from collections.abc import Callable

from django.db.models import Exists, OuterRef, Q

from coda.apps.fundingrequests.models import FundingOrganizationLink
from coda.apps.search import ScopedAlias, SearchFieldAliases
from coda.domain.fundingrequest.links import link_types
from coda.domain.institution.links import detect_ror, parse_ror
from coda.domain.publication.links import normalize_doi, parse_doi


def _link_term_query(link_type: str) -> Callable[[str], Q]:
    def term_query(value: str) -> Q:
        return Q(
            Exists(
                FundingOrganizationLink.objects.filter(
                    funding_organization_id=OuterRef("pk"),
                    type__name=link_type,
                    value__icontains=value,
                )
            )
        )

    return term_query


def _normalize_ror(value: str) -> str:
    return parse_ror(value) or value


def _aliases() -> SearchFieldAliases:
    aliases: SearchFieldAliases = {"name": "name"}

    for link_type in link_types():
        key = link_type.lower()
        term_query = _link_term_query(link_type)

        if link_type == "DOI":
            aliases[key] = ScopedAlias(
                "links__value",
                Q(),
                normalize=normalize_doi,
                detect=parse_doi,
                term_query=term_query,
            )
        elif link_type == "ROR":
            aliases[key] = ScopedAlias(
                "links__value",
                Q(),
                normalize=_normalize_ror,
                detect=detect_ror,
                term_query=term_query,
            )
        else:
            aliases[key] = ScopedAlias("links__value", Q(), term_query=term_query)

    return aliases


FUNDER_SEARCH_FIELD_ALIASES = _aliases()
