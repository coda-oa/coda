"""Tests for resolving external funder metadata to DB entities.

These tests verify how FunderRecord objects from external sources (Crossref,
DataCite) are matched to existing FundingOrganizations by DOI, Crossref ID,
or name. They are distinct from funder CRUD/business logic tests.
"""

import pytest

from coda.apps.fundingrequests.models import FundingOrganization as FundingOrganizationModel
from coda.apps.fundingrequests.models import FundingOrganizationLink, FundingOrganizationLinkType
from coda.contexts.fundingrequest.services.funder_resolution import resolve_funders
from coda.domain.fundingrequest import FunderRecord
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId, Doi, Link


def a_funder(*, name: str, links: tuple[Link, ...] = ()) -> FunderRecord:
    return FunderRecord(name=name, links=links)


def doi_link(value: str) -> Link:
    return Doi(value)


def crossref_link(value: str) -> Link:
    return CrossrefId(value)


@pytest.mark.django_db
def test__resolve_funders__crossref_id_matches_org_with_different_name() -> None:
    """Regression: funder matched by Crossref ID to an org with a different DB name must not raise KeyError.

    When a FunderRecord has a crossref_id that matches a pre-existing
    FundingOrganizationLink whose org.name differs from the funder's
    name, _resolve_organizations must still find the org by funder name.
    """
    crossref_type = FundingOrganizationLinkType.objects.get(name="Crossref")
    org = FundingOrganizationModel.objects.create(name="Existing Org Name")
    FundingOrganizationLink.objects.create(
        type=crossref_type, value="100000014", funding_organization=org
    )

    result = resolve_funders(
        [
            a_funder(
                name="Ministerio de Economía y Competitividad",
                links=(crossref_link("100000014"),),
            )
        ]
    )

    assert len(result) == 1
    assert isinstance(result[0], FunderRecord)
    assert result[0].name == "Ministerio de Economía y Competitividad"
    assert result[0].organization_id == FundingOrganizationId(org.pk)


@pytest.mark.django_db
def test__resolve_funders__duplicate_doi_different_names__does_not_raise_keyerror() -> None:
    """Regression: two funders sharing the same DOI but with different names must not cause KeyError.

    When multiple FunderRecord objects share the same identifier, the matched
    org is resolved for each by its own name.
    """

    result = resolve_funders(
        [
            FunderRecord(name="NSFC", links=(doi_link("10.13039/501100001809"),)),
            FunderRecord(
                name="National Natural Science Foundation of China",
                links=(doi_link("10.13039/501100001809"),),
            ),
        ]
    )

    assert len(result) == 2
    assert result[0].name == "NSFC"
    assert result[1].name == "National Natural Science Foundation of China"


@pytest.mark.django_db
def test_resolve_funders_same_funder_repeated_in_batch_creates_one_link_per_type() -> None:
    """Regression: a funder funding multiple publications in one import must not get duplicate links.

    The mass-import path aggregates all funder matches across every DOI into a
    single resolve_funders call, so the same identifier appears multiple times.
    Links must be deduplicated to one per (type, value, org).
    """

    resolve_funders(
        [
            a_funder(
                name="Funder A",
                links=(doi_link("10.13039/501100004663"), crossref_link("501100004663")),
            ),
            a_funder(
                name="Funder A",
                links=(doi_link("10.13039/501100004663"), crossref_link("501100004663")),
            ),
            a_funder(
                name="Funder A",
                links=(doi_link("10.13039/501100004663"), crossref_link("501100004663")),
            ),
        ]
    )

    org = FundingOrganizationModel.objects.get(name="Funder A")
    assert org.links.filter(value="10.13039/501100004663").count() == 1
    assert org.links.filter(value="501100004663").count() == 1


@pytest.mark.django_db
def test_resolve_funders_doi_only_funder_repeated_creates_single_doi_link() -> None:
    resolve_funders(
        [
            a_funder(name="Funder A", links=(doi_link("10.13039/501100004663"),)),
            a_funder(name="Funder A", links=(doi_link("10.13039/501100004663"),)),
            a_funder(name="Funder A", links=(doi_link("10.13039/501100004663"),)),
        ]
    )

    org = FundingOrganizationModel.objects.get(name="Funder A")
    assert org.links.filter(value="10.13039/501100004663").count() == 1
    assert org.links.filter(type__name="Crossref").count() == 0


@pytest.mark.django_db
def test_resolve_funders_crossref_only_funder_repeated_creates_single_crossref_link() -> None:
    resolve_funders(
        [
            a_funder(name="Funder A", links=(crossref_link("501100004663"),)),
            a_funder(name="Funder A", links=(crossref_link("501100004663"),)),
            a_funder(name="Funder A", links=(crossref_link("501100004663"),)),
        ]
    )

    org = FundingOrganizationModel.objects.get(name="Funder A")
    assert org.links.filter(value="501100004663").count() == 1
    assert org.links.filter(type__name="DOI").count() == 0


@pytest.mark.django_db
def test_resolve_funders_link_already_in_db_is_not_duplicated() -> None:
    crossref_type = FundingOrganizationLinkType.objects.get(name="Crossref")
    org = FundingOrganizationModel.objects.create(name="Existing Org")
    FundingOrganizationLink.objects.create(
        type=crossref_type, value="100000014", funding_organization=org
    )

    resolve_funders([a_funder(name="Other Name", links=(crossref_link("100000014"),))])

    assert FundingOrganizationLink.objects.filter(value="100000014").count() == 1


@pytest.mark.django_db
def test_resolve_funders_ror_link_is_persisted() -> None:
    """Given a FunderRecord carrying a ROR link, the ROR ID is persisted as a link.

    We already persist DOI and Crossref links; the ROR ID resolved by
    the ROR API must be persisted too so future imports can match by it.
    """

    resolve_funders([a_funder(name="Funder A", links=(Ror("https://ror.org/01pp8nd67"),))])

    org = FundingOrganizationModel.objects.get(name="Funder A")
    assert org.links.filter(type__name="ROR").count() == 1
    assert org.links.get(type__name="ROR").value == "https://ror.org/01pp8nd67"
