import pytest

from coda.apps.publishers import services
from coda.apps.publishers.models import Publisher
from tests.modelfactory import publisher as PublisherFactory


@pytest.mark.django_db
def test__find_by_name__exact_match__returns_publisher() -> None:
    """Test finding a publisher by exact name match"""
    created = PublisherFactory(name="Test Publisher")

    result = services.find_by_name("Test Publisher")

    assert result is not None
    assert isinstance(result, Publisher)
    assert result.pk == created.pk
    assert result.name == "Test Publisher"


@pytest.mark.django_db
def test__find_by_name__case_insensitive_match__returns_publisher() -> None:
    """Test finding a publisher with case-insensitive matching"""
    created = PublisherFactory(name="Test Publisher")

    result = services.find_by_name("test publisher")

    assert result is not None
    assert result.pk == created.pk
    assert result.name == "Test Publisher"


@pytest.mark.django_db
def test__find_by_name__uppercase_match__returns_publisher() -> None:
    """Test finding a publisher with uppercase input"""
    created = PublisherFactory(name="Test Publisher")

    result = services.find_by_name("TEST PUBLISHER")

    assert result is not None
    assert result.pk == created.pk
    assert result.name == "Test Publisher"


@pytest.mark.django_db
def test__find_by_name__not_found__returns_none() -> None:
    """Test that non-existent publisher returns None"""
    PublisherFactory(name="Existing Publisher")

    result = services.find_by_name("Non-existent Publisher")

    assert result is None


@pytest.mark.django_db
def test__find_by_name__whitespace_trimming__returns_publisher() -> None:
    """Test that whitespace is trimmed from input before matching"""
    created = PublisherFactory(name="Test Publisher")

    result = services.find_by_name("  Test Publisher  ")

    assert result is not None
    assert result.pk == created.pk
    assert result.name == "Test Publisher"


@pytest.mark.django_db
def test__create__basic_creation__returns_publisher_id() -> None:
    """Test creating a new publisher returns PublisherId"""
    publisher_id = services.create("New Publisher")

    assert isinstance(publisher_id, int)
    # Verify publisher was created in database
    publisher = Publisher.objects.get(pk=publisher_id)
    assert publisher.name == "New Publisher"


@pytest.mark.django_db
def test__create__whitespace_trimming__trims_before_saving() -> None:
    """Test that whitespace is trimmed from name before saving"""
    publisher_id = services.create("  Test Publisher  ")

    publisher = Publisher.objects.get(pk=publisher_id)
    assert publisher.name == "Test Publisher"


@pytest.mark.django_db
def test__create__returns_publisher_id_type() -> None:
    """Test that create returns PublisherId (NewType wrapping int)"""
    publisher_id = services.create("Another Publisher")

    # PublisherId is a NewType, so at runtime it's just an int
    # but type checkers will verify it's the correct type
    assert isinstance(publisher_id, int)
    assert publisher_id > 0


@pytest.mark.django_db
def test__find_by_name__duplicate_case_insensitive__returns_first() -> None:
    """When multiple publishers match case-insensitively, return the first without crashing."""
    first = PublisherFactory(name="Elsevier")
    PublisherFactory(name="elsevier")

    result = services.find_by_name("Elsevier")

    assert result is not None
    assert result.pk == first.pk


@pytest.mark.django_db
def test__find_by_name_contains__matches_substring() -> None:
    PublisherFactory(name="Springer Nature")
    PublisherFactory(name="Elsevier")

    results = list(services.find_by_name_contains("spring"))

    assert len(results) == 1
    assert results[0].name == "Springer Nature"


@pytest.mark.django_db
def test__find_by_name_contains__is_case_insensitive() -> None:
    PublisherFactory(name="Springer Nature")

    results = list(services.find_by_name_contains("SPRINGER"))

    assert len(results) == 1


@pytest.mark.django_db
def test__find_by_name_contains__returns_results_sorted_by_name() -> None:
    PublisherFactory(name="Zebra Press")
    PublisherFactory(name="Alpha Press")

    results = list(services.find_by_name_contains("press"))

    assert [r.name for r in results] == ["Alpha Press", "Zebra Press"]


@pytest.mark.django_db
def test__find_by_name_contains__no_match__returns_empty() -> None:
    PublisherFactory(name="Springer Nature")

    results = list(services.find_by_name_contains("wiley"))

    assert results == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "search_term",
    ["", "   ", "\t"],
)
def test__find_by_name_contains__empty_or_whitespace__returns_all_publishers(
    search_term: str,
) -> None:
    PublisherFactory(name="Springer Nature")
    PublisherFactory(name="Elsevier")

    results = list(services.find_by_name_contains(search_term))

    assert len(results) == 2


@pytest.mark.django_db
def test__find_by_name_contains__multi_word_search__each_word_matches_independently() -> None:
    PublisherFactory(name="Springer Nature")

    results = list(services.find_by_name_contains("Spr Natur"))

    assert len(results) == 1
    assert results[0].name == "Springer Nature"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("search_term",),
    [
        ("  Springer",),
        ("Springer  ",),
        ("  Springer  ",),
    ],
)
def test__find_by_name_contains__leading_or_trailing_whitespace__still_found(
    search_term: str,
) -> None:
    PublisherFactory(name="Springer Nature")

    results = list(services.find_by_name_contains(search_term))

    assert len(results) == 1
    assert results[0].name == "Springer Nature"
