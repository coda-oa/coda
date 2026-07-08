"""Tests for resolving external funder metadata to DB entities.

These tests verify how FunderMatch objects from external sources (Crossref,
DataCite) are matched to existing FundingOrganizations by DOI, Crossref ID,
or name. They are distinct from funder CRUD/business logic tests.
"""

import pytest

from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId


@pytest.mark.django_db
def test__resolve_funders__crossref_id_matches_org_with_different_name() -> None:
    """Regression: funder matched by Crossref ID to an org with a different DB name must not raise KeyError.

    When a FunderMatch has a crossref_id that matches a pre-existing
    FundingOrganizationLink whose org.name differs from the funder's
    name, _build_resolved_funders must still find the org by funder name.
    """
    from coda.contexts.fundingrequest.services.funder_resolver import (
        FunderMatch,
        ResolvedFunder,
        resolve_funders,
    )

    crossref_type = FundingOrganizationLinkType.objects.get(name="Crossref")
    org = FundingOrganization.objects.create(name="Existing Org Name")
    FundingOrganizationLink.objects.create(
        type=crossref_type, value="100000014", funding_organization=org
    )

    result = resolve_funders(
        [
            FunderMatch(
                name="Ministerio de Economía y Competitividad",
                funder_doi="",
                crossref_id="100000014",
            )
        ]
    )

    assert len(result) == 1
    assert isinstance(result[0], ResolvedFunder)
    assert result[0].funder.name == "Ministerio de Economía y Competitividad"
    assert result[0].organization_id == FundingOrganizationId(org.pk)


@pytest.mark.django_db
def test__resolve_funders__duplicate_doi_different_names__does_not_raise_keyerror() -> None:
    """Regression: two funders sharing the same DOI but with different names must not cause KeyError.

    When multiple FunderMatch objects share the same funder_doi, the internal
    doi_to_funder dict collapses them, potentially losing a name from the lookup.
    _persist_new_doi_links must still resolve all funder names.
    """
    from coda.contexts.fundingrequest.services.funder_resolver import (
        FunderMatch,
        resolve_funders,
    )

    result = resolve_funders(
        [
            FunderMatch(name="NSFC", funder_doi="10.13039/501100001809", crossref_id=""),
            FunderMatch(
                name="National Natural Science Foundation of China",
                funder_doi="10.13039/501100001809",
                crossref_id="",
            ),
        ]
    )

    assert len(result) == 2
    assert result[0].funder.name == "NSFC"
    assert result[1].funder.name == "National Natural Science Foundation of China"
