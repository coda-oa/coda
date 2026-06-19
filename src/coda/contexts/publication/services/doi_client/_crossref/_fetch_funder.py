from typing import Any

import httpx

from coda.contexts.publication.dto.external_metadata import ExternalFundingOrganisationMetadata
from coda.domain.publication.links import Doi

from ..errors import map_to_doi_error


def fetch_funder(doi: Doi) -> ExternalFundingOrganisationMetadata:
    """
    'prefLabel': {
        'Label': {
            'literalForm': {'lang': 'en', 'content': 'National Science Foundation'},
            'about': 'http://data.crossref.org/fundingdata/vocabulary/Label-36515'
        }
    },
    """
    try:
        response = httpx.get(doi.url(), follow_redirects=True).raise_for_status()
        content: dict[str, Any] = response.json()
        name: str = content["prefLabel"]["Label"]["literalForm"]["content"]
        return ExternalFundingOrganisationMetadata(name=name, identifiers=[str(doi)])
    except Exception as e:
        raise map_to_doi_error(e, doi) from e
