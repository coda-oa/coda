import pytest

from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization
from coda.apps.fundingrequests.models import FundingOrganizationLink, FundingOrganizationLinkType
from coda.apps.fundingrequests.services.funder_services import (
    can_delete_funding_organization,
    archive_funding_organization,
    restore_funding_organization,
    delete_funding_organization,
)
from tests import modelfactory


@pytest.mark.django_db
def test__can_delete_funder_with_no_external_funding(funder: FundingOrganization) -> None:
    can_delete, blocking = can_delete_funding_organization(funder)

    assert can_delete is True
    assert blocking == []


@pytest.mark.django_db
def test__cannot_delete_funder_with_external_funding(funder: FundingOrganization) -> None:
    funding_request = modelfactory.fundingrequest()
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=funder,
        project_id="proj-1",
        project_name="Project 1",
    )

    can_delete, blocking = can_delete_funding_organization(funder)

    assert can_delete is False
    assert "1 funding request(s)" in blocking[0]


@pytest.mark.django_db
def test__can_delete_funder__when_archived__returns_false(
    archived_funder: FundingOrganization,
) -> None:
    can_delete, blocking = can_delete_funding_organization(archived_funder)

    assert can_delete is False
    assert any("archived" in reason.lower() for reason in blocking)


@pytest.mark.django_db
def test__delete_funder__when_archived__raises_error(
    archived_funder: FundingOrganization,
) -> None:
    with pytest.raises(ValueError, match="archived"):
        delete_funding_organization(archived_funder)

    assert FundingOrganization.all_objects.filter(pk=archived_funder.pk).exists()


@pytest.mark.django_db
def test__archive_funder__sets_archived_at(funder: FundingOrganization) -> None:
    archive_funding_organization(funder)

    funder.refresh_from_db()
    assert funder.archived_at is not None


@pytest.mark.django_db
def test__archive_funder__raises_error_if_already_archived(funder: FundingOrganization) -> None:
    archive_funding_organization(funder)

    with pytest.raises(ValueError, match="already archived"):
        archive_funding_organization(funder)


@pytest.mark.django_db
def test__restore_funder__clears_archived_at(funder: FundingOrganization) -> None:
    archive_funding_organization(funder)

    restore_funding_organization(funder)

    funder.refresh_from_db()
    assert funder.archived_at is None


@pytest.mark.django_db
def test__restore_funder__raises_error_if_not_archived(funder: FundingOrganization) -> None:
    with pytest.raises(ValueError, match="not archived"):
        restore_funding_organization(funder)


@pytest.mark.django_db
def test__delete_funder_with_no_external_funding__deletes(funder: FundingOrganization) -> None:
    delete_funding_organization(funder)

    assert not FundingOrganization.all_objects.filter(pk=funder.pk).exists()


@pytest.mark.django_db
def test__delete_funder_with_external_funding__raises_error(funder: FundingOrganization) -> None:
    funding_request = modelfactory.fundingrequest()
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=funder,
        project_id="proj-1",
        project_name="Project 1",
    )

    with pytest.raises(ValueError, match="Cannot delete"):
        delete_funding_organization(funder)

    assert FundingOrganization.all_objects.filter(pk=funder.pk).exists()


@pytest.mark.django_db
def test__delete_funder__cascades_to_links(funder: FundingOrganization) -> None:
    link_type = FundingOrganizationLinkType.objects.get(name="DOI")
    FundingOrganizationLink.objects.create(
        funding_organization=funder, type=link_type, value="10.1234/test"
    )
    pk = funder.pk

    delete_funding_organization(funder)

    assert not FundingOrganizationLink.objects.filter(funding_organization_id=pk).exists()
