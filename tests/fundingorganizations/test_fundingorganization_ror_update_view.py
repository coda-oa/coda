import json

import httpx
import pytest
from coda.apps.fundingrequests.services.funder_services import update_funder_from_ror
from coda.contexts.fundingrequest.services.funder_resolution.ror_client.ror_client import (
    HttpGetClient,
)
from coda.domain.publication.links import CrossrefId, Link
from tests import modelfactory
from tests.contexts.fundingrequest.services.test_ror_client import FakeHttpGet

from coda.contexts.fundingrequest.services.funder_resolution.ror_client.ror_client import RORClient
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.institution.links import Ror

BMFTR_NAME = "Bundesministerium für Forschung, Technologie und Raumfahrt"
BMFTR_RESPONSE = """{
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

ALL_LINKS = [Ror("https://ror.org/04pz7b180"), CrossrefId("501100002347")]


@pytest.mark.django_db
@pytest.mark.parametrize("given_link", ALL_LINKS)
@pytest.mark.parametrize("http_client", [FakeHttpGet(json_data=json.loads(BMFTR_RESPONSE)), httpx])
def test__given_outdated_funding_organization_with_link__request_ror_update__updates_organization_information_via_ror_api(
    given_link: Link, http_client: HttpGetClient
) -> None:
    old_name = "Bundesministerium für Bildung und Forschung"
    org = modelfactory.funding_organization(name=old_name)
    org.set_links([given_link])
    org.save()

    ror_client = RORClient(http_client=http_client)

    update_funder_from_ror(FundingOrganizationId(org.pk), ror_client)

    org.refresh_from_db()
    assert org.name == BMFTR_NAME
    assert org.get_links() == ALL_LINKS
