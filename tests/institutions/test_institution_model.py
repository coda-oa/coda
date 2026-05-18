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


@pytest.mark.django_db
def test__is_descendant_of__exceeds_depth_limit__raises() -> None:
    """A chain of 102 institutions (101 levels deep) exceeds the depth limit."""
    chain = [Institution.objects.create(name="Level 0")]
    for i in range(1, 102):
        chain.append(Institution.objects.create(name=f"Level {i}", parent=chain[-1]))

    with pytest.raises(ValueError, match="exceeds maximum depth"):
        chain[-1].is_descendant_of(chain[0])


@pytest.mark.django_db
def test__is_descendant_of__exactly_100_levels__succeeds() -> None:
    """A chain of 101 institutions (100 levels deep) is within the depth limit."""
    chain = [Institution.objects.create(name="Level 0")]
    for i in range(1, 101):
        chain.append(Institution.objects.create(name=f"Level {i}", parent=chain[-1]))

    assert chain[-1].is_descendant_of(chain[0]) is True


@pytest.mark.django_db
def test__bulk_update__intra_batch_cycle__raises() -> None:
    """Intra-batch cycle: A→B→C→A within the same bulk_update call."""
    a = Institution.objects.create(name="A")
    b = Institution.objects.create(name="B", parent=a)
    c = Institution.objects.create(name="C", parent=b)

    # Make all three form a cycle: a→b, b→c, c→a
    a.parent = b
    b.parent = c
    c.parent = a

    with pytest.raises(ValueError, match="cycle"):
        Institution.all_objects.bulk_update([a, b, c], fields=["parent"])


@pytest.mark.django_db
def test__is_descendant_of__unsaved_intermediate_parent__returns_stale_result() -> None:
    """
    is_descendant_of queries the DB for intermediate ancestors, so it misses
    in-memory parent changes that haven't been saved yet.

    DB state:  A (no parent), B (no parent), C.parent=B
    In memory: b.parent = a  (not saved)

    c.is_descendant_of(a) should be True (C→B→A), but returns False because
    _walk_ancestor_ids fetches B from the DB where B.parent is still None.
    """
    a = Institution.objects.create(name="A")
    b = Institution.objects.create(name="B")
    c = Institution.objects.create(name="C", parent=b)

    b.parent = a  # dirty — not saved

    assert c.is_descendant_of(a) is True  # fix works: follows b.parent=a in memory


@pytest.mark.django_db
def test__bulk_update__cycle_with_parent_not_in_batch__raises() -> None:
    """Cycle completed by a parent existing in DB but not in the batch."""
    root = Institution.objects.create(name="Root")
    middle = Institution.objects.create(name="Middle", parent=root)

    # leaf is not in the batch; setting root→middle→leaf→root requires DB lookup
    leaf = Institution.objects.create(name="Leaf", parent=middle)

    root.parent = leaf

    with pytest.raises(ValueError, match="cycle"):
        Institution.all_objects.bulk_update([root], fields=["parent"])
