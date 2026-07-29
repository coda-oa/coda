"""Tests for the FundingOrganization domain type."""

from coda.domain.fundingrequest import FundingOrganization, FundingOrganizationId
from coda.domain.institution.links import Isni, Ringgold, Ror
from coda.domain.publication.links import CrossrefId

ROR_1 = "https://ror.org/04pz7b180"
ROR_2 = "https://ror.org/0134qgb15"


def test__revised__given_name_and_links__returns_copy_with_new_name_and_merged_links() -> None:
    funder = FundingOrganization(
        name="Old Name",
        links=(CrossrefId("501100004937"), Isni("000000000000000X")),
    )

    revised = funder.revised(
        name="New Name",
        links=[Ror(ROR_1), CrossrefId("501100002347")],
    )

    assert revised.name == "New Name"
    assert Ror(ROR_1) in revised.links
    assert CrossrefId("501100002347") in revised.links
    assert Isni("000000000000000X") in revised.links
    assert CrossrefId("501100004937") not in revised.links
    assert len(revised.links) == 3


def test__revised__given_only_name__keeps_existing_links() -> None:
    funder = FundingOrganization(
        name="Old Name",
        links=(CrossrefId("501100004937"),),
    )

    revised = funder.revised(name="New Name")

    assert revised.name == "New Name"
    assert revised.links == (CrossrefId("501100004937"),)


def test__revised__given_only_links__keeps_existing_name() -> None:
    funder = FundingOrganization(
        name="Old Name",
        links=(CrossrefId("501100004937"),),
    )

    revised = funder.revised(links=[Ror(ROR_1)])

    assert revised.name == "Old Name"
    assert Ror(ROR_1) in revised.links


def test__revised__given_no_args__returns_same_instance() -> None:
    funder = FundingOrganization(name="Name", links=(CrossrefId("501100004937"),))

    revised = funder.revised()

    assert revised is funder


def test__revised__original_is_not_mutated() -> None:
    funder = FundingOrganization(
        name="Old Name",
        links=(CrossrefId("501100004937"),),
    )

    funder.revised(name="New Name", links=[Ror(ROR_1)])

    assert funder.name == "Old Name"
    assert funder.links == (CrossrefId("501100004937"),)


def test__revised__preserves_organization_id() -> None:
    funder = FundingOrganization(
        name="Old Name",
        links=(CrossrefId("501100004937"),),
        organization_id=FundingOrganizationId(42),
    )

    revised = funder.revised(name="New Name")

    assert revised.organization_id == FundingOrganizationId(42)


def test__revised__given_links_of_same_type__overrides_existing() -> None:
    funder = FundingOrganization(
        name="Name",
        links=(Ror(ROR_2), CrossrefId("501100004937")),
    )

    revised = funder.revised(links=[Ror(ROR_1)])

    assert Ror(ROR_1) in revised.links
    assert Ror(ROR_2) not in revised.links
    assert CrossrefId("501100004937") in revised.links
    assert len(revised.links) == 2


def test__revised__given_no_existing_links__returns_only_new_links() -> None:
    funder = FundingOrganization(name="test", links=())

    result = funder.revised(links=[Ror(ROR_1)])

    assert result.links == (Ror(ROR_1),)


def test__revised__given_links_of_new_types__preserves_existing_and_adds_new() -> None:
    funder = FundingOrganization(
        name="Name",
        links=(CrossrefId("501100004937"),),
    )

    revised = funder.revised(links=[Ror(ROR_1), Ringgold("123")])

    assert Ror(ROR_1) in revised.links
    assert Ringgold("123") in revised.links
    assert CrossrefId("501100004937") in revised.links
    assert len(revised.links) == 3


def test__with_id__returns_copy_with_organization_id() -> None:
    funder = FundingOrganization(name="Name", links=())

    result = funder.with_id(organization_id=FundingOrganizationId(42))

    assert result.organization_id == FundingOrganizationId(42)
    assert result.name == "Name"
    assert result.links == ()


def test__with_id__does_not_mutate_original() -> None:
    funder = FundingOrganization(name="Name", links=())

    funder.with_id(organization_id=FundingOrganizationId(42))

    assert funder.organization_id is None
