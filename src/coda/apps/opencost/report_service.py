import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from django.db import transaction
from django.db.models import Prefetch
from coda.apps.contracts.models import Contract
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import Position
from coda.apps.opencost.data_aggregation import (
    get_publications_for_period,
    get_contracts_for_period,
    get_invoices_for_period,
    build_institution_hierarchy_cache,
)
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportContractSecondaryIdentifier,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportPublicationContract,
    OpenCostReportInvoice,
    OpenCostReportPublicationLink,
)
from coda.apps.publications.models import Publication
from coda.apps.preferences.models import GlobalPreferences


logger = logging.getLogger(__name__)


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


class PublicationSnapshotData(NamedTuple):
    """Collected data for bulk-creating publication snapshots."""

    # Core fields
    publication: Publication
    title: str
    doi: str
    publication_type: str
    publisher: str
    journal: str
    external_costsplitting: bool | None
    institution_name: str

    # Child data (to be bulk-created)
    identifiers: list[tuple[str, str]]  # [(type, value), ...]
    links: list[tuple[str, str]]  # [(type, value), ...] (excluding DOI)
    attached_contracts: list[tuple[Contract, int]]  # [(contract, year), ...]
    invoice_data: dict[int, list[Position]]  # {invoice_id: [positions]}


class ContractSnapshotData(NamedTuple):
    """Collected data for bulk-creating contract snapshots."""

    contract: Contract
    contract_name: str
    institution_name: str
    participation_from: date | None
    participation_to: date | None
    primary_identifier_value: str
    group_id: str  # UUID for invoice grouping

    # Child data (to be bulk-created)
    institution_identifiers: list[tuple[str, str]]
    secondary_identifiers: list[tuple[str, str]]
    invoice_data: dict[int, list[Position]]  # {invoice_id: [positions]}


@transaction.atomic
def generate_report(title: str, period_start: date, period_end: date) -> OpenCostReport:
    """
    Generate OpenCost report using bulk operations for maximum performance.

    Architecture:
    1. SETUP: Create report, build caches, fetch source data
    2. COLLECT: Extract all snapshot data (NO DB writes)
    3. BULK CREATE: Insert all primary records
    4. BULK CREATE CHILDREN: Insert all child records
    5. UPDATE: Link publications to contracts via group IDs

    Performance: ~50-80 queries regardless of dataset size
    """
    logger.info(f"Starting OpenCost report generation: '{title}' ({period_start} to {period_end})")

    # SETUP PHASE
    report = OpenCostReport.objects.create(
        title=title, period_start=period_start, period_end=period_end
    )
    logger.debug(f"Created report record: {report.id}")

    home_institution_cache = _build_home_institution_cache()
    invoices_in_period = get_invoices_for_period(start_date=period_start, end_date=period_end)

    # DATA AGGREGATION PHASE
    logger.info("Fetching publications and contracts...")
    publications = get_publications_for_period(
        start_date=period_start, end_date=period_end, invoices_in_period=invoices_in_period
    )
    contracts = get_contracts_for_period(
        start_date=period_start, end_date=period_end, invoices_in_period=invoices_in_period
    )
    logger.debug(f"Fetched {len(publications)} publications, {len(contracts)} contracts")

    # Build institution hierarchy cache (2-3 queries)
    institution_cache = build_institution_hierarchy_cache(publications)

    # COLLECTION PHASE: Build snapshot data (NO database queries)
    logger.info("Collecting snapshot data...")

    pub_snapshots: list[PublicationSnapshotData] = []
    for publication in publications:
        snapshot_data = _collect_publication_snapshot_data(
            publication, home_institution_cache, institution_cache
        )
        pub_snapshots.append(snapshot_data)

    contract_snapshots: list[ContractSnapshotData] = []
    for contract in contracts:
        contract_snapshot_data = _collect_contract_snapshot_data(contract, home_institution_cache)
        contract_snapshots.append(contract_snapshot_data)

    logger.debug(
        f"Collected {len(pub_snapshots)} publication snapshots, "
        f"{len(contract_snapshots)} contract snapshots"
    )

    # BULK CREATE PHASE
    logger.info("Bulk creating report snapshots...")

    report_publications = _bulk_create_report_publications(report, pub_snapshots)
    report_contracts = _bulk_create_report_contracts(report, contract_snapshots)

    _bulk_create_publication_children(pub_snapshots, report_publications)
    _bulk_create_contract_children(contract_snapshots, report_contracts)

    # GROUP ID UPDATE PHASE
    logger.info("Updating publication-contract group IDs...")
    _update_publication_contract_group_ids(report)

    logger.info(
        f"Completed OpenCost report generation: {report.id} "
        f"({report.publications.count()} publications, {report.contracts.count()} contracts)"
    )

    return report


def _build_home_institution_cache() -> HomeInstitutionCache:
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
    # Prefetch links with types in a single query
    links = institution.links.filter(type__name__in=["ROR", "ISNI", "Ringold"]).select_related(
        "type"
    )
    for link in links:
        identifier_type = link.type.name.lower()
        identifiers.append((identifier_type, link.value))

    return HomeInstitutionCache(institution_name=institution_name, identifiers=identifiers)


def _collect_publication_snapshot_data(
    publication: Publication,
    home_institution_cache: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> PublicationSnapshotData:
    """
    Collect all data needed for publication snapshot WITHOUT any DB writes.

    Uses ONLY prefetched data and caches - NO additional queries.

    Args:
        publication: Publication with all relationships prefetched
        home_institution_cache: Cached home institution data
        institution_cache: Cached institution hierarchy data

    Returns:
        PublicationSnapshotData with all fields and child data ready for bulk creation
    """
    # Extract DOI (uses prefetched links)
    doi_link = next(
        (link for link in publication.links.all() if link.type.name == "DOI"),
        None,
    )
    doi_value = doi_link.value if doi_link else ""

    # Extract publisher and journal (uses prefetched relations)
    if publication.article_journal:
        publisher_name = publication.article_journal.publisher.name
        journal_name = publication.article_journal.title
    elif publication.monograph_publisher:
        publisher_name = publication.monograph_publisher.name
        journal_name = ""
    else:
        publisher_name = ""
        journal_name = ""

    # Extract publication type
    pub_type_name = publication.publication_type.name if publication.publication_type else ""

    # Get institution data (uses cache, no additional queries)
    institution_name, institution_identifiers = _get_institution_data(
        publication, home_institution_cache, institution_cache
    )

    # Collect links (exclude DOI, it's stored separately)
    # Uses prefetched links - no additional queries
    links = [
        (link.type.name.lower(), link.value)
        for link in publication.links.all()
        if link.type.name.lower() != "doi"
    ]

    # Collect attached contracts (uses prefetched data)
    attached_contracts = [
        (attached.contract, attached.contract_year)
        for attached in publication.attached_contracts.all()
    ]

    # Group positions by invoice (uses prefetched data)
    invoice_data: dict[int, list[Position]] = {}
    for position in publication.position_set.all():
        invoice_id = position.invoice.id
        if invoice_id not in invoice_data:
            invoice_data[invoice_id] = []
        invoice_data[invoice_id].append(position)

    return PublicationSnapshotData(
        publication=publication,
        title=publication.title,
        doi=doi_value,
        publication_type=pub_type_name,
        publisher=publisher_name,
        journal=journal_name,
        external_costsplitting=publication.external_costsplitting,
        institution_name=institution_name,
        identifiers=institution_identifiers,
        links=links,
        attached_contracts=attached_contracts,
        invoice_data=invoice_data,
    )


def _collect_contract_snapshot_data(
    contract: Contract,
    home_institution_cache: HomeInstitutionCache,
) -> ContractSnapshotData:
    """
    Collect all data needed for contract snapshot WITHOUT any DB writes.

    Uses ONLY prefetched data - NO additional queries.

    Args:
        contract: Contract with all relationships prefetched
        home_institution_cache: Cached home institution data

    Returns:
        ContractSnapshotData with all fields and child data ready for bulk creation
    """
    # Get institution data from cache
    institution_name = home_institution_cache.institution_name
    institution_identifiers = home_institution_cache.identifiers

    # Get primary identifier (ESAC) - uses prefetched links
    primary_id = _get_contract_primary_identifier(contract)

    # Get secondary identifiers (OAI, EZB, Local) - uses prefetched links
    secondary_identifiers = _get_contract_secondary_identifiers(contract)

    # Group positions by invoice (uses prefetched data)
    invoice_data: dict[int, list[Position]] = {}
    for position in contract.position_set.all():
        invoice_id = position.invoice.id
        if invoice_id not in invoice_data:
            invoice_data[invoice_id] = []
        invoice_data[invoice_id].append(position)

    # Generate unique group ID for this contract's invoices
    group_id = str(uuid.uuid4())

    return ContractSnapshotData(
        contract=contract,
        contract_name=contract.name,
        institution_name=institution_name,
        participation_from=contract.start_date,
        participation_to=contract.end_date,
        primary_identifier_value=primary_id,
        group_id=group_id,
        institution_identifiers=institution_identifiers,
        secondary_identifiers=secondary_identifiers,
        invoice_data=invoice_data,
    )


def _bulk_create_report_publications(
    report: OpenCostReport,
    pub_snapshots: list[PublicationSnapshotData],
) -> dict[int, OpenCostReportPublication]:
    """
    Bulk create all report publication records.

    Args:
        report: The report to attach publications to
        pub_snapshots: List of collected publication data

    Returns:
        Dictionary mapping publication.id -> OpenCostReportPublication

    Performance: 1 query regardless of number of publications
    """
    if not pub_snapshots:
        logger.debug("No publications to create")
        return {}

    logger.info(f"Bulk creating {len(pub_snapshots)} report publications")

    # Build all objects in memory
    report_pubs_to_create = [
        OpenCostReportPublication(
            report=report,
            publication=snap.publication,
            title=snap.title,
            doi=snap.doi,
            publication_type=snap.publication_type,
            publisher=snap.publisher,
            journal=snap.journal,
            external_costsplitting=snap.external_costsplitting,
            institution_name=snap.institution_name,
        )
        for snap in pub_snapshots
    ]

    # Bulk create - Django automatically sets IDs
    created_pubs = OpenCostReportPublication.objects.bulk_create(
        report_pubs_to_create,
        batch_size=1000,
    )

    # Build lookup dictionary for child record creation
    pub_id_to_report_pub = {rp.publication_id: rp for rp in created_pubs}

    logger.debug(f"Created {len(created_pubs)} report publications")
    return pub_id_to_report_pub


def _bulk_create_publication_children(
    pub_snapshots: list[PublicationSnapshotData],
    report_publications: dict[int, OpenCostReportPublication],
) -> None:
    """
    Bulk create all child records for publications.

    Creates:
    - Institution identifiers
    - Publication links
    - Publication-contract attachments
    - Invoices and positions (via helper)

    Args:
        pub_snapshots: List of collected publication data
        report_publications: Mapping of publication_id -> OpenCostReportPublication

    Performance: ~5 queries total regardless of dataset size
    """
    logger.info("Bulk creating publication child records")

    # PHASE 1: Collect all identifiers
    identifiers_to_create = []
    for snap in pub_snapshots:
        report_pub = report_publications[snap.publication.id]
        for id_type, id_value in snap.identifiers:
            identifiers_to_create.append(
                OpenCostReportInstitutionIdentifier(
                    report_publication=report_pub,
                    identifier_type=id_type,
                    value=id_value,
                )
            )

    # PHASE 2: Collect all links
    links_to_create = []
    for snap in pub_snapshots:
        report_pub = report_publications[snap.publication.id]
        for link_type, link_value in snap.links:
            links_to_create.append(
                OpenCostReportPublicationLink(
                    report_publication=report_pub,
                    link_type=link_type,
                    value=link_value,
                )
            )

    # PHASE 3: Collect all contract attachments
    attachments_to_create = []
    for snap in pub_snapshots:
        report_pub = report_publications[snap.publication.id]
        for contract, year in snap.attached_contracts:
            attachments_to_create.append(
                OpenCostReportPublicationContract(
                    report_publication=report_pub,
                    contract=contract,
                    contract_year=year,
                    group_id="",  # Will be set in _update_publication_contract_group_ids
                )
            )

    # PHASE 4: Bulk create all (3 queries)
    if identifiers_to_create:
        OpenCostReportInstitutionIdentifier.objects.bulk_create(
            identifiers_to_create, batch_size=1000
        )
        logger.debug(f"Created {len(identifiers_to_create)} institution identifiers")

    if links_to_create:
        OpenCostReportPublicationLink.objects.bulk_create(links_to_create, batch_size=1000)
        logger.debug(f"Created {len(links_to_create)} publication links")

    if attachments_to_create:
        OpenCostReportPublicationContract.objects.bulk_create(
            attachments_to_create, batch_size=1000
        )
        logger.debug(f"Created {len(attachments_to_create)} contract attachments")

    # PHASE 5: Create invoices and positions (2 queries)
    _bulk_create_publication_invoices(pub_snapshots, report_publications)


def _bulk_create_publication_invoices(
    pub_snapshots: list[PublicationSnapshotData],
    report_publications: dict[int, OpenCostReportPublication],
) -> None:
    """
    Bulk create invoice snapshots and positions for publications.

    This is complex because positions need invoice IDs, but we only get those
    after bulk_create. We use index tracking to match positions to invoices.

    Args:
        pub_snapshots: List of collected publication data
        report_publications: Mapping of publication_id -> OpenCostReportPublication

    Performance: 2 queries (1 for invoices, 1 for positions)
    """
    logger.debug("Bulk creating publication invoices and positions")

    # PHASE 1: Collect all invoices and track metadata
    invoices_to_create = []
    invoice_metadata = []  # Track: (snapshot_idx, invoice_id, positions)

    for snap_idx, snap in enumerate(pub_snapshots):
        report_pub = report_publications[snap.publication.id]

        for invoice_id, positions in snap.invoice_data.items():
            if not positions:
                continue

            invoice = positions[0].invoice

            invoices_to_create.append(
                OpenCostReportInvoice(
                    report_publication=report_pub,
                    invoice=invoice,
                    invoice_number=invoice.number or "",
                    creditor=invoice.creditor.name if invoice.creditor else "",
                    invoice_date=invoice.date,
                )
            )

            # CRITICAL: Track which positions belong to THIS invoice (by index in list)
            # This allows us to match created invoices to their positions later
            invoice_metadata.append((snap_idx, invoice_id, positions))

    if not invoices_to_create:
        logger.debug("No publication invoices to create")
        return

    # PHASE 2: Bulk create invoices (1 query)
    created_invoices = OpenCostReportInvoice.objects.bulk_create(
        invoices_to_create, batch_size=1000
    )
    logger.debug(f"Created {len(created_invoices)} publication invoices")

    # PHASE 3: Create positions using created invoice IDs
    # KEY: Match by index - created_invoices[i] corresponds to invoice_metadata[i]
    positions_to_create = []

    for invoice_idx, (snap_idx, invoice_id, positions) in enumerate(invoice_metadata):
        # Match invoice by index (order preserved in bulk_create)
        report_invoice = created_invoices[invoice_idx]

        for position in positions:
            positions_to_create.append(
                OpenCostReportInvoicePosition(
                    report_invoice=report_invoice,
                    position=position,
                    amount=position.cost_amount,
                    currency=position.cost_currency,
                    cost_type=position.cost_type,
                    vat=Decimal(str(position.cost_amount))
                    * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal("0")),
                )
            )

    # PHASE 4: Bulk create positions (1 query)
    if positions_to_create:
        OpenCostReportInvoicePosition.objects.bulk_create(positions_to_create, batch_size=1000)
        logger.debug(f"Created {len(positions_to_create)} publication invoice positions")


def _bulk_create_report_contracts(
    report: OpenCostReport,
    contract_snapshots: list[ContractSnapshotData],
) -> dict[int, OpenCostReportContract]:
    """
    Bulk create all report contract records.

    Args:
        report: The report to attach contracts to
        contract_snapshots: List of collected contract data

    Returns:
        Dictionary mapping contract.id -> OpenCostReportContract

    Performance: 1 query regardless of number of contracts
    """
    if not contract_snapshots:
        logger.debug("No contracts to create")
        return {}

    logger.info(f"Bulk creating {len(contract_snapshots)} report contracts")

    # Build all objects in memory
    report_contracts_to_create = [
        OpenCostReportContract(
            report=report,
            contract=snap.contract,
            contract_name=snap.contract_name,
            institution_name=snap.institution_name,
            participation_from=snap.participation_from,
            participation_to=snap.participation_to,
            primary_identifier_value=snap.primary_identifier_value,
        )
        for snap in contract_snapshots
    ]

    # Bulk create - Django automatically sets IDs
    created_contracts = OpenCostReportContract.objects.bulk_create(
        report_contracts_to_create,
        batch_size=1000,
    )

    # Build lookup dictionary for child record creation
    contract_id_to_report_contract = {rc.contract_id: rc for rc in created_contracts}

    logger.debug(f"Created {len(created_contracts)} report contracts")
    return contract_id_to_report_contract


def _bulk_create_contract_children(
    contract_snapshots: list[ContractSnapshotData],
    report_contracts: dict[int, OpenCostReportContract],
) -> None:
    """
    Bulk create all child records for contracts.

    Creates:
    - Institution identifiers
    - Secondary identifiers
    - Invoices and positions (via helper)

    Args:
        contract_snapshots: List of collected contract data
        report_contracts: Mapping of contract_id -> OpenCostReportContract

    Performance: ~5 queries total regardless of dataset size
    """
    logger.info("Bulk creating contract child records")

    # PHASE 1: Collect all institution identifiers
    institution_identifiers_to_create = []
    for snap in contract_snapshots:
        report_contract = report_contracts[snap.contract.id]
        for id_type, id_value in snap.institution_identifiers:
            institution_identifiers_to_create.append(
                OpenCostReportContractInstitutionIdentifier(
                    report_contract=report_contract,
                    identifier_type=id_type,
                    value=id_value,
                )
            )

    # PHASE 2: Collect all secondary identifiers
    secondary_identifiers_to_create = []
    for snap in contract_snapshots:
        report_contract = report_contracts[snap.contract.id]
        for id_type, id_value in snap.secondary_identifiers:
            secondary_identifiers_to_create.append(
                OpenCostReportContractSecondaryIdentifier(
                    report_contract=report_contract,
                    identifier_type=id_type,
                    value=id_value,
                )
            )

    # PHASE 3: Bulk create all (2 queries)
    if institution_identifiers_to_create:
        OpenCostReportContractInstitutionIdentifier.objects.bulk_create(
            institution_identifiers_to_create, batch_size=1000
        )
        logger.debug(
            f"Created {len(institution_identifiers_to_create)} contract institution identifiers"
        )

    if secondary_identifiers_to_create:
        OpenCostReportContractSecondaryIdentifier.objects.bulk_create(
            secondary_identifiers_to_create, batch_size=1000
        )
        logger.debug(
            f"Created {len(secondary_identifiers_to_create)} contract secondary identifiers"
        )

    # PHASE 4: Create invoices and positions (2 queries)
    _bulk_create_contract_invoices(contract_snapshots, report_contracts)


def _bulk_create_contract_invoices(
    contract_snapshots: list[ContractSnapshotData],
    report_contracts: dict[int, OpenCostReportContract],
) -> None:
    """
    Bulk create invoice snapshots and positions for contracts.

    Similar to publication invoices but includes group_id and amount_invoice fields.

    Args:
        contract_snapshots: List of collected contract data
        report_contracts: Mapping of contract_id -> OpenCostReportContract

    Performance: 2 queries (1 for invoices, 1 for positions)
    """
    logger.debug("Bulk creating contract invoices and positions")

    # PHASE 1: Collect all invoices and track metadata
    invoices_to_create = []
    invoice_metadata = []  # Track: (snapshot_idx, invoice_id, positions)

    for snap_idx, snap in enumerate(contract_snapshots):
        report_contract = report_contracts[snap.contract.id]

        for invoice_id, positions in snap.invoice_data.items():
            if not positions:
                continue

            invoice = positions[0].invoice

            # Calculate total amount for contract invoice
            total_amount = sum(Decimal(str(p.cost_amount)) for p in positions)
            currency = positions[0].cost_currency if positions else ""

            invoices_to_create.append(
                OpenCostReportContractInvoice(
                    report_contract=report_contract,
                    invoice=invoice,
                    invoice_number=invoice.number or "",
                    creditor=invoice.creditor.name if invoice.creditor else "",
                    invoice_date=invoice.date,
                    amount_invoice=total_amount,
                    amount_invoice_currency=currency,
                    group_id=snap.group_id,
                )
            )

            # CRITICAL: Track which positions belong to THIS invoice (by index in list)
            invoice_metadata.append((snap_idx, invoice_id, positions))

    if not invoices_to_create:
        logger.debug("No contract invoices to create")
        return

    # PHASE 2: Bulk create invoices (1 query)
    created_invoices = OpenCostReportContractInvoice.objects.bulk_create(
        invoices_to_create, batch_size=1000
    )
    logger.debug(f"Created {len(created_invoices)} contract invoices")

    # PHASE 3: Create positions using created invoice IDs
    # KEY: Match by index - created_invoices[i] corresponds to invoice_metadata[i]
    positions_to_create = []

    for invoice_idx, (snap_idx, invoice_id, positions) in enumerate(invoice_metadata):
        # Match invoice by index (order preserved in bulk_create)
        report_invoice = created_invoices[invoice_idx]

        for position in positions:
            positions_to_create.append(
                OpenCostReportContractInvoicePosition(
                    report_contract_invoice=report_invoice,
                    position=position,
                    amount=position.cost_amount,
                    currency=position.cost_currency,
                    cost_type=position.cost_type,
                    vat=Decimal(str(position.cost_amount))
                    * (Decimal(str(position.tax_rate)) if position.tax_rate else Decimal("0")),
                )
            )

    # PHASE 4: Bulk create positions (1 query)
    if positions_to_create:
        OpenCostReportContractInvoicePosition.objects.bulk_create(
            positions_to_create, batch_size=1000
        )
        logger.debug(f"Created {len(positions_to_create)} contract invoice positions")


def _update_publication_contract_group_ids(report: OpenCostReport) -> None:
    """
    Update group_id for publication-contract links based on contract invoices.

    Optimized to use bulk queries and bulk_update to minimize database hits.

    Performance: Uses ~4 queries regardless of dataset size:
    - Query 1: Fetch all publication-contract links
    - Query 2: Fetch all report contracts
    - Query 3: Prefetch invoices (implicit via prefetch_related)
    - Query 4: Bulk update group_ids
    """
    # Query 1: Fetch all publication-contract links for this report
    pub_contract_links = list(
        OpenCostReportPublicationContract.objects.filter(
            report_publication__report=report
        ).select_related("report_publication")
    )

    if not pub_contract_links:
        return

    # Query 2: Fetch all report contracts with their invoices prefetched
    contract_ids = {link.contract_id for link in pub_contract_links}
    report_contracts = OpenCostReportContract.objects.filter(
        report=report, contract_id__in=contract_ids
    ).prefetch_related(
        Prefetch(
            "invoices",
            queryset=OpenCostReportContractInvoice.objects.order_by("invoice_date"),
        )
    )

    # Query 3 (implicit): Prefetch evaluates when we access invoices

    # Build lookup dictionary: contract_id -> first_invoice.group_id
    contract_to_group_id: dict[int, str] = {}
    for report_contract in report_contracts:
        # Access prefetched invoices (no additional query)
        invoices = list(report_contract.invoices.all())
        if invoices:
            first_invoice = invoices[0]  # Already ordered by invoice_date
            if first_invoice.group_id:
                contract_to_group_id[report_contract.contract_id] = first_invoice.group_id

    # Update links in memory
    links_to_update: list[OpenCostReportPublicationContract] = []
    for link in pub_contract_links:
        group_id = contract_to_group_id.get(link.contract_id)
        if group_id:
            link.group_id = group_id
            links_to_update.append(link)

    # Query 4: Single bulk update instead of N individual saves
    if links_to_update:
        OpenCostReportPublicationContract.objects.bulk_update(
            links_to_update,
            ["group_id"],
            batch_size=500,  # Process in batches to avoid memory issues
        )


def _get_institution_data(
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


def _get_contract_primary_identifier(contract: Contract) -> str:
    """
    Get the ESAC identifier for a contract.

    Uses prefetched links to avoid additional queries.
    """
    # Use prefetched links, filter in Python
    esac = next((link for link in contract.links.all() if link.type.name == "ESAC"), None)
    if esac:
        return esac.value
    return ""


def _get_contract_secondary_identifiers(contract: Contract) -> list[tuple[str, str]]:
    """
    Get secondary identifiers (OAI, EZB, Local) for a contract.

    Uses prefetched links to avoid additional queries.
    """
    identifiers = []
    # Use prefetched links, filter in Python
    for link in contract.links.all():
        if link.type.name in ["OAI", "EZB", "Local"]:
            identifier_type = link.type.name.lower()
            identifiers.append((identifier_type, link.value))
    return identifiers
