import json
from typing import Any, cast

import pytest

from coda.apps.fundingrequests.models import FundingOrganization
from tests import modelfactory

BMFTR_NAME = "Bundesministerium für Forschung, Technologie und Raumfahrt"

# Valid ROR IDs with correct checksums
VALID_ROR_ID = "https://ror.org/04pz7b180"
VALID_ROR_ID_2 = "https://ror.org/03yrm5c26"

BMFTR_RESPONSE_FULL = """{
  "number_of_results": 1,
  "time_taken": 1,
  "items": [
    {
      "admin": {
        "created": {
          "date": "2018-11-14",
          "schema_version": "1.0"
        },
        "last_modified": {
          "date": "2025-06-24",
          "schema_version": "2.1"
        }
      },
      "domains": [
        "bmbf.de"
      ],
      "established": 1955,
      "external_ids": [
        {
          "all": [
            "501100002347",
            "501100004937",
            "501100004404",
            "501100010571"
          ],
          "preferred": "501100002347",
          "type": "fundref"
        },
        {
          "all": [
            "grid.5586.e"
          ],
          "preferred": "grid.5586.e",
          "type": "grid"
        },
        {
          "all": [
            "0000 0004 0639 2885"
          ],
          "preferred": null,
          "type": "isni"
        },
        {
          "all": [
            "Q492234"
          ],
          "preferred": null,
          "type": "wikidata"
        }
      ],
      "id": "https://ror.org/04pz7b180",
      "links": [
        {
          "type": "website",
          "value": "https://www.bmbf.de"
        },
        {
          "type": "wikipedia",
          "value": "https://en.wikipedia.org/wiki/Federal_Ministry_of_Education_and_Research_(Germany)"
        }
      ],
      "locations": [
        {
          "geonames_details": {
            "continent_code": "EU",
            "continent_name": "Europe",
            "country_code": "DE",
            "country_name": "Germany",
            "country_subdivision_code": "NW",
            "country_subdivision_name": "North Rhine-Westphalia",
            "lat": 50.73438,
            "lng": 7.09549,
            "name": "Bonn"
          },
          "geonames_id": 2946447
        }
      ],
      "names": [
        {
          "lang": null,
          "types": [
            "acronym"
          ],
          "value": "BMBF"
        },
        {
          "lang": "de",
          "types": [
            "acronym"
          ],
          "value": "BMFTR"
        },
        {
          "lang": "de",
          "types": [
            "alias"
          ],
          "value": "Bundesministerium für Bildung und Forschung"
        },
        {
          "lang": "de",
          "types": [
            "label",
            "ror_display"
          ],
          "value": "Bundesministerium für Forschung, Technologie und Raumfahrt"
        },
        {
          "lang": "en",
          "types": [
            "alias"
          ],
          "value": "Federal Ministry of Education and Research"
        },
        {
          "lang": "en",
          "types": [
            "label"
          ],
          "value": "Federal Ministry of Research, Technology and Space"
        }
      ],
      "relationships": [
        {
          "label": "West African Science Service Centre on Climate Change and Adapted Land Use",
          "type": "child",
          "id": "https://ror.org/0134qgb15"
        },
        {
          "label": "Indo-German Science & Technology Centre",
          "type": "child",
          "id": "https://ror.org/01e312d09"
        }
      ],
      "status": "active",
      "types": [
        "funder",
        "government"
      ]
    }
  ],
  "meta": {
    "types": [
      {
        "id": "funder",
        "title": "funder",
        "count": 1
      },
      {
        "id": "government",
        "title": "government",
        "count": 1
      }
    ],
    "countries": [
      {
        "id": "de",
        "title": "Germany",
        "count": 1
      }
    ],
    "continents": [
      {
        "id": "eu",
        "title": "Europe",
        "count": 1
      }
    ],
    "statuses": [
      {
        "id": "active",
        "title": "active",
        "count": 1
      }
    ]
  }
}
"""

BMFTR_RESPONSE_MINIMAL = """{
  "number_of_results": 1,
  "time_taken": 1,
  "items": [
    {
      "id": "https://ror.org/04pz7b180",
      "names": [
        {
          "lang": "de",
          "types": ["label", "ror_display"],
          "value": "Bundesministerium für Forschung, Technologie und Raumfahrt"
        }
      ],
      "external_ids": [
        {
          "all": ["501100002347"],
          "preferred": "501100002347",
          "type": "fundref"
        }
      ],
      "links": []
    }
  ]
}
"""


@pytest.fixture
def bmftr_response() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(BMFTR_RESPONSE_FULL))


@pytest.fixture
def bmftr_response_minimal() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(BMFTR_RESPONSE_MINIMAL))


@pytest.fixture
def source_target_orgs() -> tuple[FundingOrganization, FundingOrganization]:
    source = modelfactory.funding_organization(name="Source Org")
    target = modelfactory.funding_organization(name="Target Org")
    return source, target


@pytest.fixture
def archived_funding_organization() -> FundingOrganization:
    org = modelfactory.funding_organization(name="Archived Org")
    org.archive()
    return org
