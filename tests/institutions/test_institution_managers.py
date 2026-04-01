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


@pytest.mark.django_db
def test__institution_can_have_one_successor() -> None:
    old_uni = Institution.objects.create(name="Old University")
    new_uni = Institution.objects.create(name="New University")

    old_uni.succeeded_by.add(new_uni)

    assert new_uni in old_uni.succeeded_by.all()
    assert old_uni in new_uni.predecessor_of.all()


@pytest.mark.django_db
def test__one_institution_can_split_into_multiple_successors() -> None:
    parent = Institution.objects.create(name="Mega University")
    campus_a = Institution.objects.create(name="Campus A")
    campus_b = Institution.objects.create(name="Campus B")

    parent.succeeded_by.add(campus_a, campus_b)

    assert campus_a in parent.succeeded_by.all()
    assert campus_b in parent.succeeded_by.all()
    assert parent.succeeded_by.count() == 2


@pytest.mark.django_db
def test__multiple_institutions_can_merge_into_one_successor() -> None:
    uni_a = Institution.objects.create(name="University A")
    uni_b = Institution.objects.create(name="University B")
    merged = Institution.objects.create(name="Merged University")

    uni_a.succeeded_by.add(merged)
    uni_b.succeeded_by.add(merged)

    assert merged in uni_a.succeeded_by.all()
    assert merged in uni_b.succeeded_by.all()
    assert merged.predecessor_of.count() == 2
