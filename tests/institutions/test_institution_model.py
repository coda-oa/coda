import django.db
import django.test.utils
import pytest

from coda.apps.institutions.models import Institution


@pytest.mark.django_db
def test__set_parent__self_reference__raises() -> None:
    institution = Institution.objects.create(name="University A")

    with pytest.raises(ValueError, match="cycle"):
        institution.set_parent(institution)
        institution.save()


@pytest.mark.django_db
def test__set_parent__direct_cycle__raises() -> None:
    parent = Institution.objects.create(name="Parent University")
    child = Institution.objects.create(name="Child University", parent=parent)

    with pytest.raises(ValueError, match="cycle"):
        parent.set_parent(child)
        parent.save()


@pytest.mark.django_db
def test__set_parent__indirect_cycle__raises() -> None:
    grandparent = Institution.objects.create(name="Grandparent University")
    parent = Institution.objects.create(name="Parent University", parent=grandparent)
    child = Institution.objects.create(name="Child University", parent=parent)

    with pytest.raises(ValueError, match="cycle"):
        grandparent.set_parent(child)
        grandparent.save()


@pytest.mark.django_db
def test__set_parent__valid_parent__sets_parent() -> None:
    parent = Institution.objects.create(name="Parent University")
    child = Institution.objects.create(name="Child University")

    child.set_parent(parent)

    assert child.parent == parent


@pytest.mark.django_db
def test__set_parent__none__clears_parent() -> None:
    parent = Institution.objects.create(name="Parent University")
    child = Institution.objects.create(name="Child University", parent=parent)

    child.set_parent(None)

    assert child.parent is None


@pytest.mark.django_db
def test__set_parent__descendant_as_parent__raises() -> None:
    root = Institution.objects.create(name="Root University")
    middle = Institution.objects.create(name="Middle University", parent=root)
    leaf = Institution.objects.create(name="Leaf University", parent=middle)

    with pytest.raises(ValueError, match="cycle"):
        root.set_parent(leaf)
        root.save()


@pytest.mark.django_db
def test__create_with_cycle_parent__raises() -> None:
    root = Institution.objects.create(name="Root University")
    middle = Institution.objects.create(name="Middle University", parent=root)
    leaf = Institution.objects.create(name="Leaf University", parent=middle)

    with pytest.raises(ValueError, match="cycle"):
        root.parent = leaf
        root.save()


@pytest.mark.django_db
def test__bulk_create__valid_parent__succeeds() -> None:
    parent = Institution.objects.create(name="Parent University")
    child = Institution(name="Child University", parent=parent)

    Institution.all_objects.bulk_create([child])

    child.refresh_from_db()
    assert child.parent == parent


@pytest.mark.django_db
def test__bulk_update__cycle__raises() -> None:
    root = Institution.objects.create(name="Root University")
    middle = Institution.objects.create(name="Middle University", parent=root)
    leaf = Institution.objects.create(name="Leaf University", parent=middle)

    root.parent = leaf  # would create a cycle

    with pytest.raises(ValueError, match="cycle"):
        Institution.all_objects.bulk_update([root], fields=["parent"])


@pytest.mark.django_db
def test__save__cycle_check_makes_one_select_per_depth_level() -> None:
    root = Institution.objects.create(name="Root University")
    middle = Institution.objects.create(name="Middle University", parent=root)
    child = Institution.objects.create(name="Child University", parent=middle)
    independent = Institution.objects.create(name="Independent University")

    # Reparenting child under independent is valid (no cycle)
    # is_descendant_of walks independent's chain: 1 SELECT (independent has no parent)
    with django.test.utils.CaptureQueriesContext(django.db.connection) as ctx:
        child.set_parent(independent)
        child.save()

    query_types = [q["sql"].split()[0].upper() for q in ctx.captured_queries]
    # 1 SELECT for is_descendant_of + 1 UPDATE for the save
    assert query_types == ["SELECT", "UPDATE"], f"Expected SELECT + UPDATE, got: {query_types}"


@pytest.mark.django_db
def test__bulk_update__cycle_check_makes_selects_for_parents_not_in_batch() -> None:
    root = Institution.objects.create(name="Root University")
    child = Institution.objects.create(name="Child University", parent=root)
    new_parent = Institution.objects.create(name="New Parent University")

    child.parent = new_parent  # valid reparent

    with django.test.utils.CaptureQueriesContext(django.db.connection) as ctx:
        Institution.all_objects.bulk_update([child], fields=["parent"])

    query_types = [q["sql"].split()[0].upper() for q in ctx.captured_queries]
    # 1 SELECT for cycle check (new_parent not in batch, must query DB) + 1 UPDATE
    assert query_types == ["SELECT", "UPDATE"], f"Expected SELECT + UPDATE, got: {query_types}"
