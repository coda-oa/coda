import pytest
from django.utils import timezone

from coda.apps.invoices.models import Creditor


@pytest.mark.django_db
def test__default_manager_excludes_archived() -> None:
    active = Creditor.objects.create(name="Active Creditor")
    archived = Creditor.objects.create(name="Archived Creditor")
    archived.archived_at = timezone.now()
    archived.save()

    results = Creditor.objects.all()

    assert active in results
    assert archived not in results


@pytest.mark.django_db
def test__all_objects_includes_archived() -> None:
    active = Creditor.objects.create(name="Active Creditor")
    archived = Creditor.objects.create(name="Archived Creditor")
    archived.archived_at = timezone.now()
    archived.save()

    results = Creditor.all_objects.all()

    assert active in results
    assert archived in results
