import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet
from coda.apps.authors.models import Author
from coda.apps.contracts.models import Contract, ContractLink
from coda.apps.institutions.models import Institution, InstitutionLink
from coda.apps.invoices.models import FundingAssignment, Invoice, Position
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.publications.models import Publication
from coda.apps.publications.models._links import Link
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication.publication import OpenAccessType

if TYPE_CHECKING:
    from coda.apps.opencost.report_service import InstitutionHierarchyCache

logger = logging.getLogger(__name__)


def get_publications_for_period(
    start_date: date,
    end_date: date,
    invoices_in_period: QuerySet[Invoice] | None = None,
    review_results: list[ReviewResult] | None = None,
    payment_statuses: list[fundingrequest_query.PaymentStatus] | None = None,
    labels: list[int] | None = None,
    exclude_labels: list[int] | None = None,
    payment_methods: list[PaymentMethod] | None = None,
    open_access_types: list[OpenAccessType] | None = None,
    publication_states: list[str] | None = None,
    entity_type: fundingrequest_query.PublicationEntityType | None = None,
    contract: int | None = None,
) -> QuerySet[Publication]:
    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    publication_ids_with_positions = (
        Position.objects.filter(invoice__in=invoices_in_period)
        .values_list("publication_id", flat=True)
        .distinct()
    )

    contracts_in_period = get_contracts_for_period(
        start_date,
        end_date,
        invoices_in_period=invoices_in_period,
        contract=contract,
    )

    publication_ids_attached_to_contracts = (
        Publication.objects.filter(
            attached_contracts__contract__in=contracts_in_period,
            attached_contracts__contract_year__gte=start_date.year,
            attached_contracts__contract_year__lte=end_date.year,
        )
        .values_list("id", flat=True)
        .distinct()
    )

    all_publication_ids = set(publication_ids_with_positions) | set(
        publication_ids_attached_to_contracts
    )

    # Apply funding request-side filters (mirrors CSV export semantics) when provided.
    filtered_publication_ids = _get_filtered_fundingrequest_publication_ids(
        review_results=review_results,
        payment_statuses=payment_statuses,
        labels=labels,
        exclude_labels=exclude_labels,
        payment_methods=payment_methods,
        open_access_types=open_access_types,
        publication_states=publication_states,
        entity_type=entity_type,
        contract=contract,
    )
    if filtered_publication_ids is not None:
        all_publication_ids &= filtered_publication_ids

    positions_in_period = Position.objects.filter(invoice__in=invoices_in_period).select_related(
        "invoice", "invoice__creditor"
    )

    # Prefetch publication links with their types
    links_with_types = Link.objects.select_related("type")

    # Prefetch institution links with their types
    institution_links_with_types = InstitutionLink.objects.select_related("type")

    # Prefetch authors with their affiliations and affiliation links
    authors_with_affiliation = Author.objects.select_related("affiliation").prefetch_related(
        Prefetch("affiliation__links", queryset=institution_links_with_types)
    )

    return (
        Publication.objects.filter(id__in=all_publication_ids)
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
            "attached_contracts",
            "attached_contracts__contract",
            Prefetch("position_set", queryset=positions_in_period),
        )
    )


def get_invoices_for_period(
    start_date: date,
    end_date: date,
    funding_source: FundingSourceId | None = None,
) -> QuerySet[Invoice]:
    qs = Invoice.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        status="paid",
    )

    if funding_source:
        qs = qs.filter(
            positions__funding_assignments__funding_source_id=funding_source,
        )

    return (
        qs.distinct()
        .select_related("creditor")
        .prefetch_related(
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
    )


def get_contracts_for_period(
    start_date: date,
    end_date: date,
    invoices_in_period: QuerySet[Invoice] | None = None,
    contract: int | None = None,
) -> QuerySet[Contract]:
    if invoices_in_period is None:
        invoices_in_period = get_invoices_for_period(start_date, end_date)

    contract_ids_qs = Position.objects.filter(
        invoice__in=invoices_in_period,
        contract__isnull=False,
    )
    if contract:
        contract_ids_qs = contract_ids_qs.filter(contract_id=contract)

    contract_ids = contract_ids_qs.values_list("contract_id", flat=True).distinct()

    positions_in_period = Position.objects.filter(
        invoice__in=invoices_in_period,
        contract__isnull=False,
    ).select_related("invoice", "invoice__creditor")

    # Prefetch contract links with their types
    contract_links_with_types = ContractLink.objects.select_related("type")

    return Contract.objects.filter(id__in=contract_ids).prefetch_related(
        "publishers",
        "journals",
        Prefetch("position_set", queryset=positions_in_period),
        Prefetch("links", queryset=contract_links_with_types),
    )


def _get_filtered_fundingrequest_publication_ids(
    review_results: list[ReviewResult] | None = None,
    payment_statuses: list[fundingrequest_query.PaymentStatus] | None = None,
    labels: list[int] | None = None,
    exclude_labels: list[int] | None = None,
    payment_methods: list[PaymentMethod] | None = None,
    open_access_types: list[OpenAccessType] | None = None,
    publication_states: list[str] | None = None,
    entity_type: fundingrequest_query.PublicationEntityType | None = None,
    contract: int | None = None,
) -> set[int] | None:
    criteria: list[fundingrequest_query.FundingRequestSearchCriteria] = []

    if review_results:
        criteria.append(fundingrequest_query.ReviewResultCriteria(review_results=review_results))
    if payment_statuses:
        criteria.append(
            fundingrequest_query.PaymentStatusCriteria(payment_statuses=payment_statuses)
        )
    if labels or exclude_labels:
        criteria.append(
            fundingrequest_query.LabelsSearchCriteria(
                include_labels=labels or [],
                exclude_labels=exclude_labels or [],
            )
        )
    if payment_methods:
        criteria.append(fundingrequest_query.PaymentMethodCriteria(payment_methods=payment_methods))
    if open_access_types:
        criteria.append(
            fundingrequest_query.OpenAccessTypeCriteria(open_access_types=open_access_types)
        )
    if publication_states:
        criteria.append(
            fundingrequest_query.PublicationStateCriteria(publication_states=publication_states)
        )
    if entity_type:
        criteria.append(fundingrequest_query.EntityTypeCriteria(entity_type=entity_type))
    if contract:
        criteria.append(fundingrequest_query.ContractSearchCriteria(contract=contract))

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
    institution_links_qs = (
        InstitutionLink.objects.filter(
            institution_id__in=all_institution_ids, type__name__in=["ROR", "ISNI", "Ringold"]
        )
        .select_related("type")
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
    cache: "InstitutionHierarchyCache",
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
) -> "InstitutionHierarchyCache":
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
    # Late import to avoid circular dependency
    from coda.apps.opencost.report_service import InstitutionHierarchyCache

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
