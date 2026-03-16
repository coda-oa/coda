import pytest
from django.utils import timezone

from coda.apps.institutions.models import Institution


@pytest.mark.django_db
def test__default_manager_excludes_archived() -> None:
    active = Institution.objects.create(name="Active Uni")
    archived = Institution.objects.create(name="Archived Uni")
    archived.archived_at = timezone.now()
    archived.save()

    results = Institution.objects.all()

    assert active in results
    assert archived not in results


@pytest.mark.django_db
def test__all_objects_includes_archived() -> None:
    active = Institution.objects.create(name="Active Uni")
    archived = Institution.objects.create(name="Archived Uni")
    archived.archived_at = timezone.now()
    archived.save()

    results = Institution.all_objects.all()

    assert active in results
    assert archived in results


@pytest.mark.django_db
def test__archived_only_shows_only_archived() -> None:
    active = Institution.objects.create(name="Active Uni")
    archived = Institution.objects.create(name="Archived Uni")
    archived.archived_at = timezone.now()
    archived.save()

    results = Institution.objects.archived_only()

    assert active not in results
    assert archived in results
