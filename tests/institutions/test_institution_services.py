import pytest

from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.institutions.services import (
    archive,
    can_delete_institution,
    generate_internal_id,
    get_institution_relationships,
    restore_without_children,
    restore_with_children,
)
from coda.apps.invoices.models import FundingAssignment, FundingSource, Position
from coda.apps.preferences.models import GlobalPreferences
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
    assert "1 child institution(s)" in blocking[0]


@pytest.mark.django_db
def test__cannot_delete_institution_with_links(institution: Institution) -> None:
    link_type, _ = InstitutionLinkType.objects.get_or_create(name="ROR")
    InstitutionLink.objects.create(
        institution=institution, type=link_type, value="https://ror.org/123"
    )

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert "1 identifier(s)/link(s)" in blocking[0]


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
def test__cannot_delete_institution_when_set_as_home_institution(institution: Institution) -> None:
    GlobalPreferences.objects.create(home_institution=institution)

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert "set as home institution in preferences" in blocking[0]


@pytest.mark.django_db
def test__can_delete_institution_with_unused_institution_funding_source(
    institution: Institution,
) -> None:
    FundingSource.objects.create(type="institution", institution=institution)

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is True
    assert blocking == []


@pytest.mark.django_db
def test__cannot_delete_institution_with_active_institution_funding_source(
    institution: Institution,
) -> None:
    funding_source = FundingSource.objects.create(type="institution", institution=institution)
    invoice = modelfactory.invoice()
    position = Position.objects.create(
        description="Test position",
        cost_amount=100,
        cost_currency="EUR",
        invoice=invoice,
    )
    FundingAssignment.objects.create(
        position=position,
        funding_source=funding_source,
        amount=100,
    )

    can_delete, blocking = can_delete_institution(institution)

    assert can_delete is False
    assert "1 active funding source(s)" in blocking[0]


@pytest.mark.django_db
def test__institution__archive_with_replacement__updates_home_institution() -> None:
    institution = Institution.objects.create(name="Old Home University")
    replacement = Institution.objects.create(name="New Home University")
    preferences = GlobalPreferences.objects.create(home_institution=institution)

    archive(institution, replacement=replacement)

    preferences.refresh_from_db()
    assert preferences.home_institution == replacement


@pytest.mark.django_db
def test__institution__archive__raises_error_if_already_archived() -> None:
    institution = Institution.objects.create(name="Old University")
    institution.archived_at = timezone.now()
    institution.save()

    with pytest.raises(ValueError, match="Institution is already archived"):
        archive(institution)


@pytest.mark.django_db
def test__institution__archive_without_replacement__archives_institution() -> None:
    institution = Institution.objects.create(name="Old University")

    archive(institution)

    institution.refresh_from_db()
    assert institution.archived_at is not None


@pytest.mark.django_db
def test__institution_with_children__archive_with_replacement__moves_children_to_replacement() -> (
    None
):
    parent = Institution.objects.create(name="Old University")
    child1 = Institution.objects.create(name="Child Campus 1", parent=parent)
    child2 = Institution.objects.create(name="Child Campus 2", parent=parent)
    replacement = Institution.objects.create(name="Replacement University")

    archive(parent, replacement=replacement)

    child1.refresh_from_db()
    child2.refresh_from_db()
    assert child1.parent == replacement
    assert child2.parent == replacement

    parent.refresh_from_db()
    assert parent.children.count() == 0

    assert child1 in replacement.children.all()
    assert child2 in replacement.children.all()


@pytest.mark.django_db
def test__institution__archive__makes_virtual() -> None:
    institution = Institution.objects.create(name="Test University", virtual=False)

    archive(institution)

    institution.refresh_from_db()
    assert institution.virtual is True


@pytest.mark.django_db
def test__institution__archive__makes_institution_virtual() -> None:
    institution = Institution.objects.create(name="Old University", virtual=False)

    archive(institution)

    institution.refresh_from_db()
    assert institution.virtual is True


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


@pytest.mark.django_db
def test__cannot_archive_home_institution_without_replacement() -> None:
    institution = Institution.objects.create(name="Home University")
    GlobalPreferences.objects.create(home_institution=institution)

    with pytest.raises(
        ValueError,
        match="Cannot archive home institution without replacement",
    ):
        archive(institution)


@pytest.mark.django_db
def test__institution_with_children__archive_institution__archives_all_children_recursively() -> (
    None
):
    faculty = Institution.objects.create(name="Faculty of Science")
    department = Institution.objects.create(name="Department of Biology", parent=faculty)
    research_group = Institution.objects.create(name="Genetics Lab", parent=department)

    archive(faculty)

    faculty.refresh_from_db()
    department.refresh_from_db()
    research_group.refresh_from_db()

    assert faculty.archived_at is not None
    assert department.archived_at is not None
    assert research_group.archived_at is not None


@pytest.mark.django_db
def test__institution_with_children__archive_institution__all_get_same_timestamp() -> None:
    parent = Institution.objects.create(name="Faculty")
    child1 = Institution.objects.create(name="Department 1", parent=parent)
    child2 = Institution.objects.create(name="Department 2", parent=parent)

    archive(parent)

    parent.refresh_from_db()
    child1.refresh_from_db()
    child2.refresh_from_db()

    assert parent.archived_at == child1.archived_at
    assert parent.archived_at == child2.archived_at


@pytest.mark.django_db
def test__institution_with_children__archive_institution__all_become_virtual() -> None:
    parent = Institution.objects.create(name="Faculty", virtual=False)
    child = Institution.objects.create(name="Department", parent=parent, virtual=False)

    archive(parent)

    parent.refresh_from_db()
    child.refresh_from_db()

    assert parent.virtual is True
    assert child.virtual is True


@pytest.mark.django_db
def test__archived_institution__restore_without_children__becomes_active() -> None:
    institution = Institution.objects.create(
        name="Archived Department",
        archived_at=timezone.now(),
        virtual=True,
    )

    restore_without_children(institution)

    institution.refresh_from_db()
    assert institution.archived_at is None
    assert institution.virtual is False


@pytest.mark.django_db
def test__archived_institution_tree__restore_with_children__all_become_active() -> None:
    # Create a 3-level hierarchy, all archived
    faculty = Institution.objects.create(
        name="Faculty of Science",
        archived_at=timezone.now(),
        virtual=True,
    )
    department = Institution.objects.create(
        name="Department of Biology",
        parent=faculty,
        archived_at=timezone.now(),
        virtual=True,
    )
    lab = Institution.objects.create(
        name="Genetics Lab",
        parent=department,
        archived_at=timezone.now(),
        virtual=True,
    )

    restore_with_children(faculty)

    faculty.refresh_from_db()
    department.refresh_from_db()
    lab.refresh_from_db()
    assert faculty.archived_at is None
    assert faculty.virtual is False
    assert department.archived_at is None
    assert department.virtual is False
    assert lab.archived_at is None
    assert lab.virtual is False


@pytest.mark.django_db
def test__archived_institution__restore_with_children_with_new_parent__parent_updated() -> None:
    # Faculty and Department archived
    old_faculty = Institution.objects.create(name="Old Faculty")
    new_faculty = Institution.objects.create(name="New Faculty")
    department = Institution.objects.create(
        name="Department",
        parent=old_faculty,
        archived_at=timezone.now(),
        virtual=True,
    )

    restore_with_children(department, new_parent=new_faculty)

    department.refresh_from_db()
    assert department.archived_at is None
    assert department.parent == new_faculty


def test__generate_internal_id__id_generated__has_correct_format() -> None:
    internal_id = generate_internal_id()

    assert internal_id.startswith("inst_")
    assert len(internal_id) == 13  # inst_ (5) + 8 chars


def test__generate_internal_id__multiple_generated__all_ids_unique() -> None:
    ids = {generate_internal_id() for _ in range(1000)}

    assert len(ids) == 1000


def test__generate_internal_id__id_generated__uses_url_safe_characters() -> None:
    internal_id = generate_internal_id()
    id_part = internal_id.replace("inst_", "")

    remaining = id_part.replace("-", "").replace("_", "")

    assert remaining.isalnum(), f"ID part '{id_part}' contains non-URL-safe characters"


@pytest.mark.django_db
def test__archive__with_descendant_as_replacement__raises() -> None:
    """Archiving a parent with its descendant as replacement must raise."""
    parent = Institution.objects.create(name="Parent")
    child = Institution.objects.create(name="Child", parent=parent)

    with pytest.raises(ValueError, match="cycle"):
        archive(parent, replacement=child)


@pytest.mark.django_db
def test__archive__with_self_as_replacement__raises() -> None:
    """Archiving an institution with itself as replacement must raise."""
    institution = Institution.objects.create(name="Institution")

    with pytest.raises(ValueError, match="cycle"):
        archive(institution, replacement=institution)


@pytest.mark.django_db
def test__archive__with_sibling_as_replacement__succeeds() -> None:
    """Archiving with a non-descendant (sibling) as replacement succeeds."""
    root = Institution.objects.create(name="Root")
    parent = Institution.objects.create(name="Parent", parent=root)
    sibling = Institution.objects.create(name="Sibling", parent=root)
    child = Institution.objects.create(name="Child", parent=parent)

    archive(parent, replacement=sibling)

    parent.refresh_from_db()
    child.refresh_from_db()
    sibling.refresh_from_db()

    assert parent.archived_at is not None
    assert child.parent == sibling
    assert sibling.parent == root


@pytest.mark.django_db
def test__walk__on_cyclic_hierarchy__raises() -> None:
    """Walk must detect and raise on DB-level cycle (bypassed via QuerySet.update)."""
    a = Institution.objects.create(name="A")
    b = Institution.objects.create(name="B", parent=a)

    # Create cycle by bypassing save(): a → b → a
    Institution.objects.filter(pk=a.pk).update(parent=b)

    with pytest.raises(ValueError, match="Cycle detected"):
        list(a.walk())


@pytest.mark.django_db
def test__archive_tree__on_cyclic_hierarchy__raises() -> None:
    """Archive must detect and raise on DB-level cycle in the tree."""
    a = Institution.objects.create(name="A")
    b = Institution.objects.create(name="B", parent=a)

    # Create cycle by bypassing save(): a → b → a
    Institution.objects.filter(pk=a.pk).update(parent=b)

    with pytest.raises(ValueError, match="Cycle detected"):
        archive(a)
