import logging
from collections.abc import Collection, Iterable
from datetime import date
from typing import NamedTuple

from django.db.models import Model, Prefetch, QuerySet
from django.db.models.functions import Lower

from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract, ContractLink
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.institutions.models import Institution, InstitutionLink
from coda.apps.invoices import invoice_query
from coda.apps.invoices.models import FundingAssignment, Invoice, Position
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models import AttachedContract, Publication
from coda.apps.publications.models._links import Link
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId, PaymentStatus

logger = logging.getLogger(__name__)

# Every shared report prefetch pins its order: the generated XML joins
# snapshot rows positionally, so the legacy XML order rode the snapshot Meta
# orderings, and an unsorted live-prefetch order must never leak into the XML —
#   * positions by (cost_amount, id): the snapshot 'amount' column was copied from
#     Position.cost_amount, whose legacy Meta ordering ["amount"] had no tie-breaker;
#     the id tie-break is its deterministic completion
#   * publication/contract links and institution identifiers by (type name, value),
#     mirroring the legacy snapshot Metas ["link_type"/"identifier_type", "value"]
#   * attached contracts by contract_year (legacy earliest-year pick)


def key_by_id[Entity: Model](entities: Iterable[Entity]) -> dict[int, Entity]:
    """Index entities by primary key.

    Report results join onto entities by FK id, never by iteration order: the
    by-ids fetches below have no defined order (``Publication``/``Contract``
    define no ``Meta.ordering``).
    """
    return {entity.pk: entity for entity in entities}


class HomeInstitutionCache(NamedTuple):
    """Cached home institution data to avoid repeated GlobalPreferences queries."""

    institution_name: str
    identifiers: list[tuple[str, str]]


class InstitutionHierarchyCache:
    """
    In-memory cache of institution hierarchies to eliminate N+1 queries.

    Stores all institutions and their links that will be accessed during
    report generation, supporting arbitrary depth parent hierarchies.
    """

    def __init__(self) -> None:
        self._institutions: dict[int, Institution] = {}
        self._links: dict[int, list[tuple[str, str]]] = {}
        self._parent_ids: dict[int, int | None] = {}

    def add_institution(
        self, institution: Institution, links: list[tuple[str, str]], parent_id: int | None
    ) -> None:
        """Add institution data to cache."""
        self._institutions[institution.id] = institution
        self._links[institution.id] = links
        self._parent_ids[institution.id] = parent_id

    def get_institution_with_identifiers(
        self, institution_id: int
    ) -> tuple[str, list[tuple[str, str]]] | None:
        """
        Get institution name and identifiers, walking up parent chain until identifiers found.

        Returns (name, identifiers) or None if institution not in cache.
        """
        current_id: int | None = institution_id

        while current_id is not None:
            if current_id not in self._institutions:
                return None

            institution = self._institutions[current_id]
            identifiers = self._links.get(current_id, [])

            if identifiers:
                return (institution.name, identifiers)

            current_id = self._parent_ids.get(current_id)

        # No identifiers found in entire chain
        if institution_id in self._institutions:
            return (self._institutions[institution_id].name, [])

        return None

    @property
    def size(self) -> int:
        """Return number of cached institutions (for logging)."""
        return len(self._institutions)

    @property
    def total_links(self) -> int:
        """Return total number of cached links (for logging)."""
        return sum(len(links) for links in self._links.values())


def select_publication_ids(
    params: fundingrequest_query.FundingRequestSearchParams,
    invoices_in_period: QuerySet[Invoice] | None = None,
) -> set[int]:
    """Ids of the publications in scope for the period of ``params``.

    The union of publications holding positions on in-period invoices and
    publications attached (within the period's year bounds) to contracts in
    period, intersected with the funding-request-side filters of ``params`` when
    any are set. Entity fetching is :func:`fetch_publications_by_ids`.
    """
    # Extract date range – must be provided
    if params.date_range is None:
        raise ValueError("date_range is required for select_publication_ids")
    start_date = params.date_range.start
    end_date = params.date_range.end

    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    publication_ids_with_positions = (
        Position.objects.filter(invoice__in=invoices_in_period)
        .values_list("publication_id", flat=True)
        .distinct()
    )

    contract_ids_in_period = select_contract_ids(
        start_date,
        end_date,
        invoices_in_period=invoices_in_period,
        contract=params.contract_id,
    )

    publication_ids_attached_to_contracts = (
        Publication.objects.filter(
            attached_contracts__contract__in=contract_ids_in_period,
            attached_contracts__contract_year__gte=start_date.year,
            attached_contracts__contract_year__lte=end_date.year,
        )
        .values_list("id", flat=True)
        .distinct()
    )

    all_publication_ids = set(publication_ids_with_positions) | set(
        publication_ids_attached_to_contracts
    )

    # Apply funding request-side filters using the shared params
    filtered_publication_ids = _get_filtered_fundingrequest_publication_ids(params)
    if filtered_publication_ids is not None:
        all_publication_ids &= filtered_publication_ids

    return all_publication_ids


def fetch_publications_by_ids(
    publication_ids: Collection[int],
    positions: QuerySet[Position] | None = None,
) -> QuerySet[Publication]:
    """Fetch publications by id with the report's prefetch shape.

    ``positions`` overrides the ``position_set`` prefetch: generation passes a
    period-bound queryset, while the default loads every live position —
    regeneration feeds pinned ids and re-reads positions live.
    """
    if positions is None:
        positions = Position.objects.select_related("invoice", "invoice__creditor")

    links_with_types = Link.objects.select_related("type").order_by("type__name", "value")
    institution_links_with_types = InstitutionLink.objects.select_related("type").order_by(
        "type__name", "value"
    )
    authors_with_affiliation = (
        Author.objects.select_related("affiliation")
        .prefetch_related(Prefetch("affiliation__links", queryset=institution_links_with_types))
        .order_by("id")
    )

    return (
        Publication.objects.filter(id__in=publication_ids)
        .select_related(
            "article_journal",
            "article_journal__publisher",
            "monograph_publisher",
            "publication_type",
            "fundingrequest",
        )
        .prefetch_related(
            Prefetch("links", queryset=links_with_types),
            Prefetch("relevant_authors", queryset=authors_with_affiliation),
            Prefetch(
                "attached_contracts",
                queryset=AttachedContract.objects.select_related("contract").order_by(
                    "contract_year"
                ),
            ),
            Prefetch("position_set", queryset=positions.order_by("cost_amount", "id")),
        )
    )


def get_publications_for_period(
    params: fundingrequest_query.FundingRequestSearchParams,
    invoices_in_period: QuerySet[Invoice] | None = None,
) -> QuerySet[Publication]:
    # Extract date range – must be provided
    if params.date_range is None:
        raise ValueError("date_range is required for get_publications_for_period")
    start_date = params.date_range.start
    end_date = params.date_range.end

    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    publication_ids = select_publication_ids(params, invoices_in_period=invoices_in_period)

    positions_in_period = Position.objects.filter(invoice__in=invoices_in_period).select_related(
        "invoice", "invoice__creditor"
    )

    return fetch_publications_by_ids(publication_ids, positions=positions_in_period)


def get_invoices_for_period(
    start_date: date,
    end_date: date,
    funding_source: FundingSourceId | None = None,
) -> QuerySet[Invoice]:
    params = invoice_query.InvoiceSearchParams(
        date_range=DateRange(start_date, end_date),
        payment_status=PaymentStatus.Paid,
        funding_source=funding_source,
    )
    criteria = invoice_query.build_criteria(params)
    qs = invoice_query.search(*criteria)

    return _with_invoice_prefetches(qs)


def fetch_invoices_by_ids(invoice_ids: Collection[int]) -> QuerySet[Invoice]:
    """Fetch invoices by id with the same prefetch shape as
    :func:`get_invoices_for_period`, but no period and no paid-status filter —
    regeneration loads pinned invoices by pinned id only.
    """
    return _with_invoice_prefetches(Invoice.objects.filter(id__in=invoice_ids))


def _with_invoice_prefetches(queryset: QuerySet[Invoice]) -> QuerySet[Invoice]:
    """Apply the report's one invoice prefetch shape to an invoice queryset."""
    return queryset.select_related("creditor").prefetch_related(
        "positions",
        Prefetch(
            "positions__funding_assignments",
            queryset=FundingAssignment.objects.select_related("funding_source"),
        ),
        "positions__publication",
        "positions__publication__article_journal",
        "positions__publication__article_journal__publisher",
        "positions__publication__monograph_publisher",
    )


def select_contract_ids(
    start_date: date,
    end_date: date,
    invoices_in_period: QuerySet[Invoice] | None = None,
    contract: int | None = None,
) -> set[int]:
    """Ids of the contracts holding positions on in-period invoices, optionally
    narrowed to a single contract id. Entity fetching is
    :func:`fetch_contracts_by_ids`.
    """
    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    contract_ids_qs = Position.objects.filter(
        invoice__in=invoices_in_period,
        contract__isnull=False,
    )
    if contract:
        contract_ids_qs = contract_ids_qs.filter(contract_id=contract)

    return set(contract_ids_qs.values_list("contract_id", flat=True).distinct())


def fetch_contracts_by_ids(
    contract_ids: Collection[int],
    positions: QuerySet[Position] | None = None,
) -> QuerySet[Contract]:
    """Fetch contracts by id with the report's prefetch shape.

    ``positions`` overrides the ``position_set`` prefetch: generation passes a
    period-bound queryset, while the default loads every live position —
    regeneration feeds pinned ids and re-reads positions live.
    """
    if positions is None:
        positions = Position.objects.select_related("invoice", "invoice__creditor")

    # Prefetch contract links with their types
    contract_links_with_types = ContractLink.objects.select_related("type").order_by(
        "type__name", "value"
    )

    return Contract.objects.filter(id__in=contract_ids).prefetch_related(
        "publishers",
        "journals",
        Prefetch("position_set", queryset=positions.order_by("cost_amount", "id")),
        Prefetch("links", queryset=contract_links_with_types),
    )


def get_contracts_for_period(
    start_date: date,
    end_date: date,
    invoices_in_period: QuerySet[Invoice] | None = None,
    contract: int | None = None,
) -> QuerySet[Contract]:
    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    contract_ids = select_contract_ids(
        start_date,
        end_date,
        invoices_in_period=invoices_in_period,
        contract=contract,
    )

    positions_in_period = Position.objects.filter(
        invoice__in=invoices_in_period,
        contract__isnull=False,
    ).select_related("invoice", "invoice__creditor")

    return fetch_contracts_by_ids(contract_ids, positions=positions_in_period)


def _get_filtered_fundingrequest_publication_ids(
    params: fundingrequest_query.FundingRequestSearchParams,
) -> set[int] | None:
    # Exclude date_range – openCost filters by invoice/contract dates, not request_date
    params_no_date = params.without_date_range()
    criteria = fundingrequest_query.build_criteria(params_no_date)

    if not criteria:
        return None

    return set(fundingrequest_query.search(*criteria).values_list("publication_id", flat=True))


def _collect_institution_ids_from_authors(publications: QuerySet[Publication]) -> set[int]:
    """Extract institution IDs from corresponding authors (no database query)."""
    institution_ids: set[int] = set()
    for publication in publications:
        for author in publication.relevant_authors.all():
            if author.roles and "CORRESPONDING_AUTHOR" in author.roles:
                if author.affiliation_id:
                    institution_ids.add(author.affiliation_id)
                break
    return institution_ids


def _walk_parent_chain(institution_ids: set[int]) -> tuple[set[int], int]:
    """
    Walk up parent chains to find all ancestor institution IDs.

    Returns:
        Tuple of (all_institution_ids, hierarchy_levels)
    """
    all_institution_ids: set[int] = set(institution_ids)
    current_ids: set[int] = institution_ids
    max_iterations = 20
    iteration = 0

    while current_ids and iteration < max_iterations:
        iteration += 1
        logger.debug(
            f"Walking parent chain (iteration {iteration}): checking {len(current_ids)} institutions"
        )

        institutions_batch = Institution.objects.filter(id__in=current_ids).values_list(
            "id", "parent_id"
        )

        parent_ids: set[int] = set()
        for inst_id, parent_id in institutions_batch:
            if parent_id and parent_id not in all_institution_ids:
                parent_ids.add(parent_id)
                all_institution_ids.add(parent_id)

        logger.debug(f"Found {len(parent_ids)} new parent institutions at level {iteration}")
        current_ids = parent_ids

        if not parent_ids:
            break

    logger.debug(
        f"Completed parent chain walk after {iteration} levels, "
        f"total {len(all_institution_ids)} institutions"
    )

    return all_institution_ids, iteration


def _fetch_institution_links(all_institution_ids: set[int]) -> dict[int, list[tuple[str, str]]]:
    """Fetch and group institution links by institution ID."""
    # Determinism contract: the cached identifier list is explicitly sorted by
    # (type, value), mirroring the legacy snapshot Metas — an unsorted DB order
    # must never leak into the XML.
    institution_links_qs = (
        InstitutionLink.objects.filter(
            institution_id__in=all_institution_ids, type__name__in=["ROR", "ISNI", "Ringold"]
        )
        .select_related("type")
        .order_by(Lower("type__name"), "value")
        .values_list("institution_id", "type__name", "value")
    )

    links_by_institution: dict[int, list[tuple[str, str]]] = {}
    for institution_id, type_name, value in institution_links_qs:
        if institution_id not in links_by_institution:
            links_by_institution[institution_id] = []
        links_by_institution[institution_id].append((type_name.lower(), value))

    total_links = sum(len(links) for links in links_by_institution.values())
    logger.debug(f"Loaded {total_links} institution links")

    return links_by_institution


def _populate_institution_cache(
    cache: InstitutionHierarchyCache,
    institutions: dict[int, Institution],
    links_by_institution: dict[int, list[tuple[str, str]]],
) -> None:
    """Populate cache with institution data."""
    for inst_id, institution in institutions.items():
        links = links_by_institution.get(inst_id, [])
        inst_parent_id: int | None = institution.parent_id
        cache.add_institution(institution, links, inst_parent_id)


def build_institution_hierarchy_cache(
    publications: QuerySet[Publication],
) -> InstitutionHierarchyCache:
    """
    Build cache of all institutions and parent hierarchies needed for publications.

    Performs 2-3 queries total:
    1. Iteratively walk up parent chains to find all ancestor institution IDs
    2. Bulk fetch all institutions
    3. Bulk fetch all institution links with types

    Args:
        publications: QuerySet with prefetched relevant_authors

    Returns:
        InstitutionHierarchyCache with O(1) lookups for institution data
    """
    cache = InstitutionHierarchyCache()

    # Step 1: Collect initial institution IDs from corresponding authors (no query)
    institution_ids = _collect_institution_ids_from_authors(publications)

    if not institution_ids:
        logger.debug("No institutions found in publications, returning empty cache")
        return cache

    logger.debug(f"Found {len(institution_ids)} institutions from corresponding authors")

    # Step 2: Walk up parent chains to get ALL ancestor institution IDs
    all_institution_ids, hierarchy_levels = _walk_parent_chain(institution_ids)

    # Step 3: Bulk fetch all institutions
    institutions = Institution.objects.filter(id__in=all_institution_ids).in_bulk()
    logger.debug(f"Loaded {len(institutions)} institution objects")

    # Step 4: Bulk fetch all institution links with types
    links_by_institution = _fetch_institution_links(all_institution_ids)

    # Step 5: Populate cache
    _populate_institution_cache(cache, institutions, links_by_institution)

    logger.info(
        f"Built institution hierarchy cache: {cache.size} institutions, "
        f"{cache.total_links} links, {hierarchy_levels} hierarchy levels"
    )

    return cache


def build_home_institution_cache() -> HomeInstitutionCache:
    """
    Build a cache of home institution data from GlobalPreferences.

    This is queried once per report generation to avoid repeated database hits.
    Returns empty values if no home institution is configured.
    """
    prefs = GlobalPreferences.objects.select_related("home_institution").first()
    if not prefs or not prefs.home_institution:
        return HomeInstitutionCache(institution_name="", identifiers=[])

    institution = prefs.home_institution
    institution_name = institution.name

    identifiers = []
    # Prefetch links with types in a single query, in the (type, value) order the
    # report reads its institution identifiers back in.
    links = (
        institution.links.filter(type__name__in=["ROR", "ISNI", "Ringold"])
        .select_related("type")
        .order_by(Lower("type__name"), "value")
    )
    for link in links:
        identifier_type = link.type.name.lower()
        identifiers.append((identifier_type, link.value))

    return HomeInstitutionCache(institution_name=institution_name, identifiers=identifiers)


def get_institution_data(
    publication: Publication,
    home_institution_cache: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> tuple[str, list[tuple[str, str]]]:
    """
    Get institution name and identifiers for a publication's corresponding author.

    Uses institution_cache for O(1) lookups with parent chain traversal - NO database queries.
    Falls back to home_institution_cache if no corresponding author or institution found.

    Args:
        publication: Publication with prefetched relevant_authors
        home_institution_cache: Fallback home institution data
        institution_cache: Pre-built cache of all institutions and hierarchies

    Returns:
        Tuple of (institution_name, [(identifier_type, value), ...])
    """
    # Use prefetched authors, filter in Python to avoid new query
    corresponding_author = next(
        (
            author
            for author in publication.relevant_authors.all()
            if author.roles and "CORRESPONDING_AUTHOR" in author.roles
        ),
        None,
    )

    if corresponding_author and corresponding_author.affiliation_id:
        # Look up in cache (no database query!)
        # Cache handles parent chain traversal internally
        result = institution_cache.get_institution_with_identifiers(
            corresponding_author.affiliation_id
        )
        if result and result[1]:  # Only use result if it has identifiers
            return result

    # Fall back to cached home institution data
    return home_institution_cache.institution_name, home_institution_cache.identifiers
