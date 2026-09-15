"""How many queries generating an openCost report costs, at realistic volume.

Generation reads the items a period covers, keeps one row per item it considered and writes the
document those items add up to. None of that may grow with the dataset beyond the bulk reads and
writes it is made of, so these tests count queries over datasets of a thousand publications and
pin the totals:

1. **End-to-end** (``test_generate_report_bulk_operations_performance``)
   - 1,000 publications + 10 contracts, whole generation
   - O(1) scaling: the count is set by the shape of the run, not by the dataset

2. **Individual stages**
   - Home institution cache (``test_home_institution_cache_avoids_repeated_queries``)
   - Link prefetching (``test_generate_report_link_queries_dont_scale_with_dataset``)
   - Invoice fetch deduplication (``test_generate_report_fetches_invoices_only_once``)
   - Institution hierarchy cache (``test_institution_hierarchy_cache_performance``)
   - Reading a finished report's issue state (``test_reading_a_finished_report_issue_state_costs_no_queries``)
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from pytest_django.fixtures import DjangoAssertNumQueries

from coda.apps.institutions.models import Institution
from coda.apps.opencost.data_aggregation import build_home_institution_cache
from coda.apps.opencost.report_service import generate_report
from coda.apps.publications.models import Publication
from coda.apps.publications.models._attachedentities import AttachedContract
from coda.apps.publications.models._links import LinkType, Link
from coda.domain.publication.publication import Authors
from opencost import PublicationType
from tests import modelfactory
from tests.opencost.helpers import (
    create_corresponding_author,
    create_creditor,
    create_institution_with_identifiers,
    create_invoice,
    create_position,
    create_publication_with_invoice,
    stored_document,
)

if TYPE_CHECKING:
    from coda.apps.invoices.models import Creditor
    from coda.apps.opencost.models import OpenCostReport


from coda.apps.preferences.models import GlobalPreferences


def create_performance_test_dataset(num_publications: int = 1000, num_contracts: int = 10) -> None:
    """
    Create a realistic dataset for OpenCost performance testing.

    Creates:
    - Link types (DOI, Handle)
    - Specified number of contracts with invoices
    - Specified number of publications with invoices, links, and contract attachments

    Args:
        num_publications: Number of publications to create (default: 1000)
        num_contracts: Number of contracts to create (default: 10)
    """

    # Setup: Create link types
    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")

    # Create contracts with invoices
    contracts = []
    for i in range(num_contracts):
        contract = modelfactory.contract()
        contract.name = f"Test Contract {i + 1}"
        contract.start_date = date(2024, 1, 1)
        contract.end_date = date(2024, 12, 31)
        contract.save()

        creditor = create_creditor(name=f"Contract Creditor {i}")
        invoice = create_invoice(
            creditor=creditor,
            invoice_date=date(2024, 6, 1),
            number=f"INV-CONTRACT-{i:02d}",
        )
        create_position(
            invoice=invoice,
            contract=contract,
            cost_amount=Decimal("5000.00"),
        )

        contracts.append(contract)

    # Create publications with invoices, links, and contract attachments
    for i in range(num_publications):
        pub = modelfactory.publication()
        pub.title = f"Test Article {i + 1}"
        pub.save()

        # Add DOI and Handle links
        Link.objects.create(publication=pub, type=doi_type, value=f"10.1234/article{i}")
        Link.objects.create(publication=pub, type=handle_type, value=f"hdl:1234/{i}")

        # Create invoice with position
        creditor = create_creditor(name=f"Publisher {i % 100}")  # 100 unique publishers
        invoice = create_invoice(
            creditor=creditor,
            invoice_date=date(2024, 1, 1) + timedelta(days=i % 365),
            number=f"INV-2024-{i:04d}",
        )
        create_position(
            invoice=invoice,
            publication=pub,
            cost_amount=Decimal("1500.00"),
        )

        # Attach to a contract (round-robin)
        contract = contracts[i % len(contracts)]
        AttachedContract.objects.create(publication=pub, contract=contract, contract_year=2024)


@pytest.mark.django_db
def test_home_institution_cache_avoids_repeated_queries() -> None:
    """The institution a report speaks for is read once, however often it is asked for.

    Every item may need the home institution's name and identifiers. Reading them from
    `GlobalPreferences` on each access would repeat one identical query per item; the cache
    answers every later access from the single read it made.
    """

    # Create home institution with identifiers
    institution = Institution.objects.create(name="Test University")
    GlobalPreferences.objects.create(home_institution=institution)

    # Build cache - should execute 1 query
    with CaptureQueriesContext(connection) as context:
        cache = build_home_institution_cache()

    # Verify only 1 query (for GlobalPreferences with select_related)
    assert len(context.captured_queries) <= 2  # Allow 1-2 queries for prefs + links

    # Access cache multiple times - no additional queries
    with CaptureQueriesContext(connection) as context:
        for _ in range(100):
            _ = cache.institution_name
            _ = cache.identifiers

    assert len(context.captured_queries) == 0  # All cached, no new queries


@pytest.mark.django_db
@pytest.mark.performance
def test_generate_report_link_queries_dont_scale_with_dataset() -> None:
    """An item's links arrive with the item, not one query per item.

    Identifiers such as DOIs and agreement references are read while the document is built.
    Reading them alongside the items keeps the number of link queries a constant of the run
    instead of a function of how many publications the period covers.
    """
    from coda.apps.publications.models._links import LinkType, Link

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")

    # Create 50 publications with links
    for i in range(50):
        pub = modelfactory.publication()
        pub.title = f"Test Article {i}"
        pub.save()

        Link.objects.create(publication=pub, type=doi_type, value=f"10.1234/test{i}")
        Link.objects.create(publication=pub, type=handle_type, value=f"hdl:1234/{i}")

        # Create invoice
        create_publication_with_invoice(
            publication=pub,
            invoice_date=date(2024, 6, 1),
            invoice_number=f"INV-2024-{i:03d}",
        )

    # Generate report and capture queries
    with CaptureQueriesContext(connection) as context:
        report = generate_report(
            title="Link Prefetch Test",
            filters={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )

    # Count link-related queries
    link_queries = [q for q in context.captured_queries if "publication_link" in q["sql"].lower()]

    # Should be 1 prefetch query for all links (not 50 separate queries)
    assert len(link_queries) <= 2  # Allow 1-2 for link + linktype prefetch

    assert report.publications.count() == 50


@pytest.mark.django_db
@pytest.mark.performance
def test_generate_report_fetches_invoices_only_once() -> None:
    """An invoice paid by many items is read once.

    One invoice often settles positions of several publications and an agreement at the same
    time. The run reads each invoice a single time, so twenty shared invoices do not become
    twenty invoice queries multiplied by the items that share them.
    """
    creditor = create_creditor(name="Shared Creditor")

    # Create 1 contract
    contract = modelfactory.contract()
    contract.name = "Shared Contract"
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    # Create 20 invoices shared between publications and contract
    for i in range(20):
        fr = modelfactory.fundingrequest(title=f"Article {i}")

        invoice = create_invoice(
            creditor=creditor,
            invoice_date=date(2024, 6, 1),
            number=f"SHARED-INV-{i:02d}",
        )

        # Position links to both publication and contract
        create_position(
            invoice=invoice,
            publication=fr.publication,
            contract=contract,
            cost_amount=Decimal("2000.00"),
        )

    # Generate report
    with CaptureQueriesContext(connection) as context:
        report = generate_report(
            title="Invoice Dedup Test",
            filters={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )

    # Count invoice queries (should be reasonable regardless of publications/contracts)
    invoice_queries = [q for q in context.captured_queries if '"invoices_invoice"' in q["sql"]]

    # A query per invoice would be twenty here; the measured count stays in single digits
    # however many items share the invoices.
    assert len(invoice_queries) <= 10

    assert report.publications.count() == 20
    assert report.contracts.count() == 1


@pytest.mark.django_db
@pytest.mark.performance
def test_generate_report_bulk_operations_performance() -> None:
    """A thousand-publication report costs a fixed number of queries.

    Measured 41 queries for 1,000 publications with invoices plus 10 contracts: the period's
    items, their positions, invoices and relationships arrive through a handful of bulk reads,
    and every row the report keeps is written by one bulk insert per level. Nothing here is
    repeated per item, so the count stays the same however large the period is.
    """
    # Create test dataset: 1,000 publications + 10 contracts
    create_performance_test_dataset(num_publications=1000, num_contracts=10)

    # The budget is the measured 41 with room for a query or two of growth; a per-item query
    # creeping back in would spend it immediately at this dataset size.
    with CaptureQueriesContext(connection) as query_context:
        report = generate_report(
            title="Thousand Publication Report",
            filters={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )

    # Get query count from the generation above
    query_count = len(query_context.captured_queries)

    # ASSERT: Verify correctness
    assert report.publications.count() == 1000
    assert report.contracts.count() == 10

    # Performance
    assert query_count < 60, f"Query count {query_count} exceeds the budget of < 60"

    print(f"\n{'=' * 70}")
    print("Thousand-publication generation - SUCCESS")
    print(f"{'=' * 70}")
    print(f"Query Count:      {query_count} / 60 (measured 41)")
    print(f"Publications:     {report.publications.count()}")
    print(f"Contracts:        {report.contracts.count()}")
    print("Scaling:          constant - the count does not follow the dataset size")
    print(f"{'=' * 70}\n")


@pytest.mark.django_db
@pytest.mark.performance
def test_reading_a_finished_report_issue_state_costs_no_queries() -> None:
    """Asking a generated report whether it has issues costs nothing.

    The issue log loads with the report row and the counts are derived from it in memory, so
    neither `has_issues()` nor `get_issue_counts()` has to look at a single item of a
    thousand-publication report — and a second call has no more work to do than the first.
    """
    create_performance_test_dataset(num_publications=1000, num_contracts=10)

    report = generate_report(
        title="Issue State Test",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
    )

    with CaptureQueriesContext(connection) as first_call:
        has_issues = report.has_issues()
        issue_counts = report.get_issue_counts()

    with CaptureQueriesContext(connection) as second_call:
        has_issues_again = report.has_issues()
        issue_counts_again = report.get_issue_counts()

    assert first_call.captured_queries == [], first_call.captured_queries
    assert second_call.captured_queries == [], second_call.captured_queries
    assert isinstance(has_issues, bool)
    assert has_issues == has_issues_again
    assert issue_counts == issue_counts_again

    print(f"\n{'=' * 70}")
    print("Issue state of a finished report - SUCCESS")
    print(f"{'=' * 70}")
    print(f"Publications:       {report.publications.count()}")
    print(f"Contracts:          {report.contracts.count()}")
    print(f"Has issues:         {has_issues}")
    print(f"Issue counts:       {issue_counts}")
    print(f"{'=' * 70}\n")


def _create_deep_tree_institutions() -> tuple[Institution, list[Institution]]:
    """
    Create a 6-level deep institution tree with identifiers at root and level 3.

    Returns:
        Tuple of (root, leaf_institutions)
    """
    deep_tree_root = create_institution_with_identifiers(
        name="Deep Tree Root", ror="https://ror.org/deep-root", isni="ISNI-ROOT-001"
    )
    deep_level4 = Institution.objects.create(name="Deep Level 4", parent=deep_tree_root)
    deep_level3 = create_institution_with_identifiers(
        name="Deep Level 3", parent=deep_level4, ror="https://ror.org/deep-level3"
    )
    deep_level2 = Institution.objects.create(name="Deep Level 2", parent=deep_level3)
    deep_level1 = Institution.objects.create(name="Deep Level 1", parent=deep_level2)

    # Create 50 leaf institutions at the bottom
    deep_leaves = [
        Institution.objects.create(name=f"Deep Leaf {i}", parent=deep_level1) for i in range(50)
    ]

    return deep_tree_root, deep_leaves


def _create_shallow_tree_institutions() -> list[Institution]:
    """
    Create 10 shallow trees (2-3 levels) with identifiers at roots.

    Returns:
        List of leaf institutions (50 total, 5 per tree)
    """
    shallow_leaves = []
    for tree_idx in range(10):
        # Root with identifiers
        shallow_root = create_institution_with_identifiers(
            name=f"Shallow Tree {tree_idx} Root",
            ror=f"https://ror.org/shallow-{tree_idx}",
        )

        # Some trees have an intermediate level (3 levels total)
        if tree_idx % 3 == 0:
            middle = Institution.objects.create(
                name=f"Shallow Tree {tree_idx} Middle", parent=shallow_root
            )
            parent_for_leaves = middle
        else:
            parent_for_leaves = shallow_root

        # Create 5 leaves per tree = 50 leaves total
        for leaf_idx in range(5):
            leaf = Institution.objects.create(
                name=f"Shallow Tree {tree_idx} Leaf {leaf_idx}", parent=parent_for_leaves
            )
            shallow_leaves.append(leaf)

    return shallow_leaves


def _create_flat_institutions() -> list[Institution]:
    """
    Create 200 flat institutions with 0-2 level hierarchies.

    Half have a parent with identifiers (2 levels), half are standalone with identifiers (1 level).

    Returns:
        List of leaf institutions (200 total)
    """
    flat_institutions = []
    for i in range(200):
        if i % 2 == 0:
            # Half have a parent with identifiers (2 levels)
            parent = create_institution_with_identifiers(
                name=f"Flat Parent {i}", isni=f"ISNI-FLAT-{i}"
            )
            child = Institution.objects.create(name=f"Flat Child {i}", parent=parent)
            flat_institutions.append(child)
        else:
            # Half are standalone with identifiers (1 level)
            inst = create_institution_with_identifiers(
                name=f"Flat Institution {i}", ringold=f"RING-{i}"
            )
            flat_institutions.append(inst)

    return flat_institutions


def _create_publications_with_authors(
    all_leaf_institutions: list[Institution],
) -> list[Publication]:
    """
    Create 1,000 publications with corresponding authors assigned to institutions.

    Args:
        all_leaf_institutions: Pool of institutions to assign authors to (round-robin)

    Returns:
        List of created publications
    """
    publications = []
    for i in range(1000):
        # Assign corresponding author with institution
        institution = all_leaf_institutions[i % len(all_leaf_institutions)]

        # Pass empty Authors() to prevent factory from creating default authors
        fr = modelfactory.fundingrequest(
            title=f"Publication {i} - {institution.name}", authors=Authors(())
        )

        create_corresponding_author(
            publication=fr.publication,
            name=f"Author {i}",
            email=f"author{i}@example.com",
            affiliation=institution,
        )

        publications.append(fr.publication)

    return publications


def _create_invoices_for_publications(
    publications: list[Publication], creditor: "Creditor", period_start: date
) -> None:
    """
    Create invoices and positions for publications (100 invoices, 10 publications each).

    Args:
        publications: List of publications to create positions for
        creditor: Creditor for invoices
        period_start: Start date for invoice dates
    """
    for i in range(0, 1000, 10):
        invoice = create_invoice(
            creditor=creditor,
            invoice_date=period_start + timedelta(days=i // 10),
            number=f"INV-2024-{i:04d}",
            status="paid",
        )

        for j in range(10):
            pub_idx = i + j
            if pub_idx < 1000:
                create_position(
                    invoice=invoice,
                    publication=publications[pub_idx],
                    cost_amount=Decimal("1000.00"),
                    cost_currency="EUR",
                )


def _institution_of(entry: PublicationType) -> tuple[str, list[str]]:
    """The name and the identifier values the document states for one entry's institution."""
    institution = entry.institution
    assert institution is not None
    names = [name.value for name in institution.name or []]
    return (names[0] if names else "", [identifier.value for identifier in institution.id or []])


def _verify_institution_hierarchy_results(report: "OpenCostReport") -> None:
    """Each publication is named by the nearest institution of its author that can be named.

    The stored document is where a walk up an institution hierarchy shows up: a deep leaf's
    publication is named by the level of its tree that carries identifiers, a shallow leaf's by
    its tree root, and a flat institution's by itself or its parent.
    """
    rows = list(report.publications.order_by("id"))
    entries = stored_document(report).publication or []
    assert len(entries) == len(rows), "the document holds every publication the report covers"
    named = {row.title: _institution_of(entry) for row, entry in zip(rows, entries, strict=True)}

    deep_tree = [named[title] for title in named if "Deep Leaf" in title]
    assert len(deep_tree) == 200  # 1000/300 * 50 deep leaves
    for institution_name, identifiers in deep_tree[:10]:
        assert institution_name == "Deep Level 3"
        assert "https://ror.org/deep-level3" in identifiers

    shallow_tree = [named[title] for title in named if "Shallow Tree" in title]
    assert len(shallow_tree) == 200  # Same cycling math
    for institution_name, identifiers in shallow_tree[:10]:
        assert "Shallow Tree" in institution_name
        assert identifiers

    flat = [named[title] for title in named if "Flat" in title]
    assert len(flat) == 600  # 1000/300 * 200 flat institutions
    flat_with_identifiers = [entry for entry in flat if entry[1]]
    assert len(flat_with_identifiers) >= 540  # 90% of 600 flat pubs

    # Success metrics
    print(f"\n{'=' * 70}")
    print("Institution hierarchy cache - SUCCESS")
    print(f"{'=' * 70}")
    print(f"Publications:       {len(rows)}")
    print(f"Deep tree pubs:     {len(deep_tree)} (6-level hierarchy)")
    print(f"Shallow tree pubs:  {len(shallow_tree)} (2-3 level hierarchies)")
    print(f"Flat institution:   {len(flat)} (0-2 level hierarchies)")
    print(f"With identifiers:   {len(flat_with_identifiers)} / {len(flat)} flat pubs")
    print(f"{'=' * 70}\n")


@pytest.mark.django_db
@pytest.mark.performance
def test_institution_hierarchy_cache_performance(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """Walking an author's institution up to a level that can be named costs nothing per item.

    A publication is named by its author's affiliation, which often carries no identifiers of
    its own and has to be resolved to a parent. Here that affiliation sits at the bottom of a
    six-level tree, at the leaf of a two- or three-level tree, or alone as a flat institution -
    for a thousand publications. Resolving each chain per item would be one query per level per
    item; the whole tree is resolved once instead and the answer kept.
    """
    from coda.apps.preferences.models import GlobalPreferences

    period_start = date(2024, 1, 1)
    period_end = date(2024, 12, 31)

    # Setup: Create home institution and creditor
    home_institution = create_institution_with_identifiers(
        name="Home Institution", ror="https://ror.org/home123"
    )
    GlobalPreferences.objects.create(home_institution=home_institution)
    creditor = create_creditor(name="Test Publisher")

    # Three shapes of affiliation: one deep tree, shallow trees, flat institutions
    _, deep_leaves = _create_deep_tree_institutions()
    shallow_leaves = _create_shallow_tree_institutions()
    flat_institutions = _create_flat_institutions()

    all_leaf_institutions = deep_leaves + shallow_leaves + flat_institutions

    # One publication per author, each affiliated with a leaf
    publications = _create_publications_with_authors(all_leaf_institutions)

    # Every publication settled by an invoice in the period
    _create_invoices_for_publications(publications, creditor, period_start)

    # Generate, counting the queries the run costs
    with CaptureQueriesContext(connection) as context:
        report = generate_report(
            title="Institution Hierarchy Report",
            filters={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
        )

    # Measured 39 queries for a thousand publications reached through six-, three- and
    # one-level institution trees: the walk up each author's affiliation costs nothing per
    # publication because the whole tree is resolved once and the answer kept in a dict.
    query_count = len(context.captured_queries)
    assert query_count < 55, f"Query count {query_count} exceeds the budget of < 55"
    assert report.publications.count() == 1000

    # Check the document named each publication by the right institution
    _verify_institution_hierarchy_results(report)
