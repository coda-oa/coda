import pytest

from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.institutions.services import (
    archive_and_create_successor,
    archive_with_existing_successor,
    can_delete_institution,
    get_institution_relationships,
)
from tests import modelfactory
from django.utils import timezone
from coda.domain.author import InstitutionId
from coda.domain.publication import Authors
from tests import domainfactory


@pytest.fixture
def institution() -> Institution:
    return Institution.objects.create(name="Test University")


@pytest.mark.django_db
def test__can_delete_institution_with_no_relationships(institution: Institution) -> None:
    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is True
    assert blocking == []


@pytest.mark.django_db
def test__cannot_delete_institution_with_children(institution: Institution) -> None:
    _ = Institution.objects.create(name="Child", parent=institution)

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert "1 child institutions" in blocking[0]


@pytest.mark.django_db
def test__cannot_delete_institution_with_links(institution: Institution) -> None:
    link_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    InstitutionLink.objects.create(
        institution=institution, type=link_type, value="https://ror.org/123"
    )

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert "identifiers/links" in blocking[0]


@pytest.mark.django_db
def test__cannot_delete_institution_with_multiple_relationships(institution: Institution) -> None:
    _ = Institution.objects.create(name="Child", parent=institution)
    link_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    InstitutionLink.objects.create(
        institution=institution, type=link_type, value="https://ror.org/123"
    )

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert len(blocking) == 2


@pytest.mark.django_db
def test__institution__archive_and_create_successor__creates_successor_and_archives_institution() -> (
    None
):
    institution = Institution.objects.create(name="Old University")

    successor = archive_and_create_successor(institution, "New University")

    assert successor.name == "New University"
    assert successor.archived_at is None

    institution.refresh_from_db()
    assert institution.archived_at is not None
    assert successor in institution.succeeded_by.all()


@pytest.mark.django_db
def test__institution__archive_and_create_successor__raises_error_if_already_archived() -> None:
    institution = Institution.objects.create(name="Old University")
    institution.archived_at = timezone.now()
    institution.save()

    with pytest.raises(ValueError, match="Institution is already archived"):
        archive_and_create_successor(institution, "New University")


@pytest.mark.django_db
def test__institution__archive_and_create_successor__successor_is_not_archived() -> None:
    institution = Institution.objects.create(name="Old University")

    successor = archive_and_create_successor(institution, "New University")

    assert successor.archived_at is None
    assert successor.succeeded_by.count() == 0


@pytest.mark.django_db
def test__institution__archive_with_existing_successor__archives_institution_and_links_existing_institution_as_successor() -> (
    None
):
    institution = Institution.objects.create(name="Old University")
    successor = Institution.objects.create(name="New University")

    archive_with_existing_successor(institution, [successor])

    institution.refresh_from_db()
    assert institution.archived_at is not None
    assert successor in institution.succeeded_by.all()


@pytest.mark.django_db
def test__institution__archive_with_existing_successor__can_link_multiple_successors() -> None:
    institution = Institution.objects.create(name="Old University")
    successor1 = Institution.objects.create(name="New University A")
    successor2 = Institution.objects.create(name="New University B")

    archive_with_existing_successor(institution, [successor1, successor2])

    institution.refresh_from_db()
    assert institution.archived_at is not None
    assert institution.succeeded_by.count() == 2
    assert successor1 in institution.succeeded_by.all()
    assert successor2 in institution.succeeded_by.all()


@pytest.mark.django_db
def test__institution__archive_with_existing_successor__raises_error_if_already_archived() -> None:
    institution = Institution.objects.create(name="Old University")
    successor = Institution.objects.create(name="New University")
    institution.archived_at = timezone.now()
    institution.save()

    with pytest.raises(ValueError, match="Institution is already archived"):
        archive_with_existing_successor(institution, [successor])


@pytest.mark.django_db
def test__institution__archive_with_existing_successor__raises_error_if_no_successors() -> None:
    institution = Institution.objects.create(name="Old University")

    with pytest.raises(ValueError, match="Must provide at least one successor"):
        archive_with_existing_successor(institution, [])


@pytest.mark.django_db
def test__institution_without_relationships__get_institution_relationships__returns_no_relationships(
    institution: Institution,
) -> None:
    relationships = get_institution_relationships(institution)

    assert relationships.children.count() == 0
    assert relationships.funding_requests.count() == 0
    assert relationships.invoices.count() == 0
    assert relationships.links.count() == 0
    assert relationships.has_any is False


@pytest.mark.django_db
def test__institution_with_children__get_institution_relationships__returns_children(
    institution: Institution,
) -> None:
    child = Institution.objects.create(name="Child", parent=institution)

    relationships = get_institution_relationships(institution)

    assert relationships.children.count() == 1
    assert child in relationships.children
    assert relationships.has_any is True


@pytest.mark.django_db
def test__institution_with_funding_request_author_affiliation__get_institution_relationships__returns_funding_request(
    institution: Institution,
) -> None:
    author = domainfactory.author(affiliation=InstitutionId(institution.pk))
    funding_request = modelfactory.fundingrequest(authors=Authors([author]))

    relationships = get_institution_relationships(institution)

    assert relationships.funding_requests.count() == 1
    assert funding_request in relationships.funding_requests
    assert relationships.has_any is True


@pytest.mark.django_db
def test__institution_with_links__get_institution_relationships__returns_links(
    institution: Institution,
) -> None:
    link_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    link = InstitutionLink.objects.create(
        institution=institution, type=link_type, value="https://ror.org/123"
    )

    relationships = get_institution_relationships(institution)

    assert relationships.links.count() == 1
    assert link in relationships.links
    assert relationships.has_any is True
