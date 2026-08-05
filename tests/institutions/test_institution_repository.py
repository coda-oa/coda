import pytest
from django.utils import timezone

from coda.apps.institutions import repository
from coda.apps.institutions.models import Institution


@pytest.mark.django_db
def test__search__excludes_archived_by_default() -> None:
    active = Institution.objects.create(name="Active University")
    archived = Institution.objects.create(name="Archived University", archived_at=timezone.now())

    results = list(repository.search())

    assert active in results
    assert archived not in results


@pytest.mark.django_db
def test__archived_only__returns_only_archived() -> None:
    active = Institution.objects.create(name="Active University")
    archived = Institution.objects.create(name="Archived University", archived_at=timezone.now())

    results = list(repository.archived_only())

    assert archived in results
    assert active not in results


@pytest.mark.django_db
def test__search__includes_archived_when_requested() -> None:
    active = Institution.objects.create(name="Active University")
    archived = Institution.objects.create(name="Archived University", archived_at=timezone.now())

    results = list(repository.search(include_archived=True))

    assert active in results
    assert archived in results


@pytest.mark.django_db
def test__search__filters_by_name() -> None:
    Institution.objects.create(name="University of Berlin")
    Institution.objects.create(name="University of Munich")
    Institution.objects.create(name="Technical Institute")

    results = list(repository.search(name="University"))

    assert results[0].name in ["University of Berlin", "University of Munich"]
    assert results[1].name in ["University of Berlin", "University of Munich"]
    assert len(results) == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("search_term",),
    [
        ("  University",),
        ("University  ",),
        ("  University  ",),
    ],
)
def test__search__leading_or_trailing_whitespace__still_found(search_term: str) -> None:
    Institution.objects.create(name="University of Berlin")

    results = list(repository.search(name=search_term))

    assert len(results) == 1
    assert results[0].name == "University of Berlin"


@pytest.mark.django_db
def test__search__filters_by_name_and_excludes_archived() -> None:
    active = Institution.objects.create(name="Test University")
    archived = Institution.objects.create(name="Test College", archived_at=timezone.now())

    results = list(repository.search(name="Test"))

    assert active in results
    assert archived not in results


@pytest.mark.django_db
def test__search__filters_by_name_and_includes_archived() -> None:
    active = Institution.objects.create(name="Test University")
    archived = Institution.objects.create(name="Test College", archived_at=timezone.now())

    results = list(repository.search(name="Test", include_archived=True))

    assert active in results
    assert archived in results


@pytest.mark.django_db
@pytest.mark.parametrize(
    "search_term",
    ["", "   ", "\t"],
)
def test__search__empty_or_whitespace_name__returns_all_institutions(search_term: str) -> None:
    Institution.objects.create(name="University of Berlin")
    Institution.objects.create(name="Technical Institute")

    results = list(repository.search(name=search_term))

    assert len(results) == 2


@pytest.mark.django_db
def test__search__multi_word_search__each_word_matches_independently() -> None:
    Institution.objects.create(name="University of Berlin")

    results = list(repository.search(name="Uni Ber"))

    assert len(results) == 1
    assert results[0].name == "University of Berlin"


@pytest.mark.django_db
def test__hierarchical_institutions__search__returns_hierarchical_order() -> None:
    zebra = Institution.objects.create(name="Zebra University")
    bio = Institution.objects.create(name="Biology Department", parent=zebra)
    mol_lab = Institution.objects.create(name="Molecular Lab", parent=bio)
    cs = Institution.objects.create(name="Computer Science Department", parent=zebra)

    alpha = Institution.objects.create(name="Alpha University")
    math = Institution.objects.create(name="Mathematics Department", parent=alpha)

    results = list(repository.search())

    assert results.index(alpha) < results.index(zebra)
    assert results.index(math) == results.index(alpha) + 1
    assert results.index(bio) > results.index(math)
    assert results.index(bio) < results.index(cs)
    assert results.index(mol_lab) == results.index(bio) + 1
    assert results.index(cs) == results.index(mol_lab) + 1
