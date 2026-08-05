"""Seam tests: ROR resolution is persisted through both import paths.

Verifies, at the public seams a caller uses, that a funder whose Crossref ID
resolves via ROR gets a persisted ``FundingOrganizationLink`` of type ROR:

- ``DOIImportService.import_from_doi`` (single import)
- ``MassDOIImportService.import_multi`` (mass import)

Uses ``FundedArticleScenario`` (whose HZDR funder carries Crossref id
``501100008346``) and a stubbed ROR client so no live API is hit.
"""

import pytest
from tests.contexts.fundingrequest.fixtures import FundedArticleScenario
from tests.contexts.fundingrequest.fixtures._ror_stub import HZDR_CROSSREF, HZDR_ROR, StubRORClient

from coda.apps.fundingrequests.models import FundingOrganizationLink
from coda.contexts.fundingrequest.services.doi_import._mass_service import MassDOIImportService
from coda.contexts.fundingrequest.services.doi_import._repository_immediate import (
    ImmediateDOIRepository,
)
from coda.contexts.fundingrequest.services.doi_import._service import (
    DOIImportService,
    OverrideImport,
)
from coda.contexts.fundingrequest.services.funder_resolution import resolve_funders
from coda.domain.fundingrequest import FunderRecord
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId


def _assert_ror_link_persisted() -> None:
    assert FundingOrganizationLink.objects.filter(type__name="ROR", value=HZDR_ROR).count() == 1


@pytest.mark.django_db
def test__import_from_doi__ror_resolved_funder__persists_ror_link() -> None:
    """Given a single import with a resolving ROR client, a ROR link is persisted."""
    scenario = FundedArticleScenario.with_in_memory_client()
    scenario.setup_db()

    repo = ImmediateDOIRepository(ror_client=StubRORClient())
    sut = DOIImportService(scenario.client, repo=repo)
    sut.import_from_doi(scenario.doi)

    _assert_ror_link_persisted()


@pytest.mark.django_db
def test__import_multi__ror_resolved_funder__persists_ror_link() -> None:
    """Given a mass import with a resolving ROR client, a ROR link is persisted.

    This is the seam the reported bug lives at: mass import previously
    hardcoded a live ROR client and had no regression coverage here.
    """
    scenario = FundedArticleScenario.with_in_memory_client()
    scenario.setup_db()

    sut = MassDOIImportService(scenario.client)
    result = sut.import_multi(
        [(scenario.doi, OverrideImport.empty())],
        metadata_cache={},
        ror_client=StubRORClient(),
    )

    assert len(result.imported) == 1
    _assert_ror_link_persisted()


@pytest.mark.django_db
def test__resolve_funders__ror_record__appends_ror_link() -> None:
    """Given a ROR record for a funder's Crossref ID, resolve_funders adds a Ror link."""
    matches = resolve_funders(
        [FunderRecord(name="HZDR", links=(CrossrefId(HZDR_CROSSREF),))],
        ror_client=StubRORClient(),
    )

    assert len(matches) == 1
    assert Ror(HZDR_ROR) in matches[0].links
