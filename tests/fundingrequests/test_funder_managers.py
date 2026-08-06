import pytest
from django.utils import timezone

from coda.apps.fundingrequests.models import FundingOrganization


@pytest.mark.django_db
def test__default_manager_excludes_archived() -> None:
    active = FundingOrganization.objects.create(name="Active Funder")
    archived = FundingOrganization.objects.create(
        name="Archived Funder", archived_at=timezone.now()
    )

    results = FundingOrganization.objects.all()

    assert active in results
    assert archived not in results


@pytest.mark.django_db
def test__all_objects_includes_archived() -> None:
    active = FundingOrganization.objects.create(name="Active Funder")
    archived = FundingOrganization.objects.create(
        name="Archived Funder", archived_at=timezone.now()
    )

    results = FundingOrganization.all_objects.all()

    assert active in results
    assert archived in results


@pytest.mark.django_db
def test__archive_sets_archived_at() -> None:
    org = FundingOrganization.objects.create(name="Test Funder")
    org.archive()

    org.refresh_from_db()
    assert org.archived_at is not None


@pytest.mark.django_db
def test__restore_clears_archived_at() -> None:
    org = FundingOrganization.objects.create(name="Test Funder", archived_at=timezone.now())
    org.restore()

    org.refresh_from_db()
    assert org.archived_at is None
