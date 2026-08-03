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
from tests.fundingorganizations.conftest import BMFTR_NAME, BMFTR_RESPONSE_FULL

ALL_LINKS = [Ror("https://ror.org/04pz7b180"), CrossrefId("501100002347")]


@pytest.mark.django_db
@pytest.mark.parametrize("given_link", ALL_LINKS)
@pytest.mark.parametrize("http_client", [FakeHttpGet(json_data=BMFTR_RESPONSE_FULL), httpx])
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
