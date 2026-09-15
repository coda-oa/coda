import logging
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone

import opencost
from coda.apps.contracts.models import Contract
from coda.apps.invoices.models import Invoice, Position
from coda.apps.opencost.data_aggregation import (
    HomeInstitutionCache,
    InstitutionHierarchyCache,
    build_home_institution_cache,
    build_institution_hierarchy_cache,
    fetch_contracts_by_ids,
    fetch_invoices_by_ids,
    fetch_publications_by_ids,
    get_contracts_for_period,
    get_institution_data,
    get_invoices_for_period,
    get_publications_for_period,
    key_by_id,
)
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInstitutionIdentifier,
    OpenCostReportContractInvoice,
    OpenCostReportContractInvoicePosition,
    OpenCostReportContractSecondaryIdentifier,
    OpenCostReportInstitutionIdentifier,
    OpenCostReportInvoice,
    OpenCostReportInvoicePosition,
    OpenCostReportPublication,
    OpenCostReportPublicationContract,
    OpenCostReportPublicationLink,
)
from coda.apps.opencost.services.issues import collect_issues
from coda.apps.opencost.transformers.contract import (
    get_contract_primary_identifier,
    secondary_identifiers_from_links,
)
from coda.apps.opencost.transformers.live import (
    InvoiceOutcome,
    ItemOutcome,
    transform_report,
)
from coda.apps.publications.models import Publication
from coda.contexts.exports.dto.filters import ExportFiltersDto

logger = logging.getLogger(__name__)


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


logger = logging.getLogger(__name__)


def generate_report(
    title: str,
    filters: dict[str, Any],
) -> OpenCostReport:
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
    dto = ExportFiltersDto.model_validate(filters)
    params = dto.to_params()

    if params.date_range is None:
        raise ValueError("date_range is required for generate_report")
    start_date = params.date_range.start
    end_date = params.date_range.end

    logger.info(f"Starting OpenCost report generation: '{title}' ({start_date} to {end_date})")

    # SETUP PHASE
    report = OpenCostReport.objects.create(
        title=title,
        period_start=start_date,
        period_end=end_date,
        filters=dto.to_storage(),
    )
    logger.debug(f"Created report record: {report.id}")

    home_institution_cache = build_home_institution_cache()
    invoices_in_period = get_invoices_for_period(
        start_date=start_date,
        end_date=end_date,
        funding_source=params.funding_source,
    )

    # DATA AGGREGATION PHASE
    logger.info("Fetching publications and contracts...")
    publications = get_publications_for_period(
        params=params,
        invoices_in_period=invoices_in_period,
    )
    contracts = get_contracts_for_period(
        start_date=start_date,
        end_date=end_date,
        invoices_in_period=invoices_in_period,
        contract=params.contract_id,
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
    for contract_obj in contracts:
        contract_snapshot_data = _collect_contract_snapshot_data(
            contract_obj, home_institution_cache
        )
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

    # ISSUE COUNTS PHASE - dry run the transform and persist the resulting counts.
    # _update_publication_contract_group_ids(report) runs before this dry run
    # because the transformer reads the persisted group ids (transformers.py
    # _get_contract_cost_data - invoice group id - and _get_part_of_contract -
    # link group id) while collecting issues.
    logger.info("Computing issue counts...")

    issues = collect_issues(report)
    if issues is not None:
        report.errors_count = sum(1 for w in issues if w.level == "error")
        report.warnings_count = sum(1 for w in issues if w.level == "warning")
        report.save(update_fields=["errors_count", "warnings_count"])
    else:
        # A broken check must not take generation down: leave the counts untouched.
        logger.warning(
            "OpenCost issue check failed for report %s; counts left unchanged", report.pk
        )

    # ARTIFACT PHASE - the document itself, its issue log and how every row fared, built
    # from the same live data the snapshot above was collected from.
    logger.info("Storing openCost artifact...")
    _store_artifact(report, invoices_in_period, home_institution_cache, institution_cache)

    logger.info(
        f"Completed OpenCost report generation: {report.id} "
        f"({report.publications.count()} publications, {report.contracts.count()} contracts) "
        f"[{report.errors_count} errors, {report.warnings_count} warnings]"
    )

    return report


def regenerate_report(report: OpenCostReport) -> OpenCostReport:
    """Rebuild the report's document from current CODA data, over the stored membership.

    The seed rows are the report's frozen item list: publications, contracts and invoices are
    re-fetched by pinned id and the stored filters are never consulted, so nothing joins or
    leaves the scope. Everything below the item level is live - titles, links, identifiers,
    institution hierarchies, the home institution and the positions on pinned invoices - so a
    corrected ESAC id, an amended invoice or a previously unset home institution flows through.
    Positions newly found on a pinned invoice get their parent-invoice link row inserted, so a
    live cost is never silently unexported.

    Concurrent regenerates serialize on the report row. Unlike the generation pass, a failure
    here is raised to the caller: with no fallback artifact in play, a broken regenerate must
    be heard, not logged and swallowed.
    """
    logger.info(f"Regenerating openCost artifact for report {report.id}")

    with transaction.atomic():
        locked = OpenCostReport.objects.select_for_update().get(pk=report.pk)
        _regenerate_artifact(locked)

    report.refresh_from_db()
    return report


def _regenerate_artifact(report: OpenCostReport) -> None:
    """The artifact pass re-run over the report's own rows, inside the locked transaction."""
    report_publications = list(report.publications.order_by("id"))
    report_contracts = list(report.contracts.order_by("id"))

    invoice_ids = set(
        OpenCostReportInvoice.objects.filter(
            report_publication__in=report_publications
        ).values_list("invoice_id", flat=True)
    ) | set(
        OpenCostReportContractInvoice.objects.filter(
            report_contract__in=report_contracts
        ).values_list("invoice_id", flat=True)
    )

    # Positions are re-read live, but only on pinned invoices: invoice membership stays frozen,
    # so a cost on an invoice outside the report can never enter it here.
    positions_on_pinned_invoices = Position.objects.filter(invoice__in=invoice_ids).select_related(
        "invoice", "invoice__creditor"
    )
    live_publications_qs = fetch_publications_by_ids(
        {row.publication_id for row in report_publications},
        positions=positions_on_pinned_invoices,
    )
    live_publications = key_by_id(live_publications_qs)
    live_contracts = key_by_id(
        fetch_contracts_by_ids(
            {row.contract_id for row in report_contracts},
            positions=positions_on_pinned_invoices.filter(contract__isnull=False),
        )
    )
    live_invoices = key_by_id(fetch_invoices_by_ids(invoice_ids))

    _insert_missing_invoice_links(
        report_publications, live_publications, report_contracts, live_contracts
    )

    # Read the (possibly extended) invoice rows after the link insertion, so the transform
    # iterates and counts every invoice a parent now holds a position on.
    report_publications = list(report.publications.order_by("id").prefetch_related("invoices"))
    report_contracts = list(report.contracts.order_by("id").prefetch_related("invoices"))
    publication_invoices = [
        report_invoice for row in report_publications for report_invoice in row.invoices.all()
    ]
    contract_invoices = [
        report_invoice for row in report_contracts for report_invoice in row.invoices.all()
    ]

    # The home institution is a CODA object like every other: read fresh, never stored.
    home_institution_cache = build_home_institution_cache()
    institution_cache = build_institution_hierarchy_cache(live_publications_qs)

    transform = transform_report(
        report=report,
        publications=report_publications,
        contracts=report_contracts,
        live_publications=live_publications,
        live_contracts=live_contracts,
        live_invoices=live_invoices,
        home_institution=home_institution_cache,
        institution_cache=institution_cache,
    )

    report.xml_content = "" if transform.data is None else opencost.to_xml(transform.data)
    report.issues = [asdict(warning) for warning in transform.issues]
    # The stored issue log is the counts' source once read paths serve it, so the two
    # are written together: a regeneration that clears the log must also clear the
    # counts, or the union count properties - and every badge - keep answering from
    # the columns of the run that produced the old log.
    report.errors_count = sum(1 for w in transform.issues if w.level == "error")
    report.warnings_count = sum(1 for w in transform.issues if w.level == "warning")
    report.generated_at = timezone.now()
    report.save(
        update_fields=["xml_content", "issues", "errors_count", "warnings_count", "generated_at"]
    )

    _store_publication_outcomes(report_publications, transform.publications)
    _store_contract_outcomes(report_contracts, transform.contracts)
    _store_publication_invoice_outcomes(publication_invoices, transform.publication_invoices)
    _store_contract_invoice_outcomes(contract_invoices, transform.contract_invoices)


def _insert_missing_invoice_links(
    report_publications: list[OpenCostReportPublication],
    live_publications: Mapping[int, Publication],
    report_contracts: list[OpenCostReportContract],
    live_contracts: Mapping[int, Contract],
) -> None:
    """Create the parent-invoice link rows that live positions imply but the tables lack.

    A fix inside a pinned invoice can give a parent a position on a pinned invoice it had none
    on before; without the link row the transform would never see that cost. Item scope is
    untouched - both levels of every inserted row already exist - and the unique_together keeps
    repeated regenerations idempotent.
    """
    existing_publication_links = set(
        OpenCostReportInvoice.objects.filter(
            report_publication__in=report_publications
        ).values_list("report_publication_id", "invoice_id")
    )
    publication_links = [
        OpenCostReportInvoice(report_publication_id=row.id, invoice_id=invoice_id)
        for row in report_publications
        for invoice_id in sorted(
            {
                position.invoice_id
                for position in live_publications[row.publication_id].position_set.all()
            }
        )
        if (row.id, invoice_id) not in existing_publication_links
    ]
    OpenCostReportInvoice.objects.bulk_create(publication_links)

    existing_contract_links = set(
        OpenCostReportContractInvoice.objects.filter(
            report_contract__in=report_contracts
        ).values_list("report_contract_id", "invoice_id")
    )
    contract_links = [
        OpenCostReportContractInvoice(report_contract_id=row.id, invoice_id=invoice_id)
        for row in report_contracts
        for invoice_id in sorted(
            {position.invoice_id for position in live_contracts[row.contract_id].position_set.all()}
        )
        if (row.id, invoice_id) not in existing_contract_links
    ]
    OpenCostReportContractInvoice.objects.bulk_create(contract_links)


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
    institution_name, institution_identifiers = get_institution_data(
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

    # Get external_costsplitting from funding request if it exists
    external_costsplitting = None
    if hasattr(publication, "fundingrequest") and publication.fundingrequest:
        external_costsplitting = publication.fundingrequest.external_costsplitting

    return PublicationSnapshotData(
        publication=publication,
        title=publication.title,
        doi=doi_value,
        publication_type=pub_type_name,
        publisher=publisher_name,
        journal=journal_name,
        external_costsplitting=external_costsplitting,
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
    primary_id = get_contract_primary_identifier(contract)

    # Get secondary identifiers (OAI, EZB, Local) - uses prefetched links
    secondary_identifiers = secondary_identifiers_from_links(contract)

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


def _collect_publication_invoice_data(
    pub_snapshots: list[PublicationSnapshotData],
    report_publications: dict[int, OpenCostReportPublication],
) -> tuple[list[OpenCostReportInvoice], list[tuple[int, int, list[Position]]]]:
    """
    Collect invoice objects ready for bulk creation and track metadata.

    Returns:
        Tuple of (invoices_to_create, invoice_metadata)
        where invoice_metadata is [(snap_idx, invoice_id, positions), ...]
    """
    invoices_to_create = []
    invoice_metadata = []

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

            # Track which positions belong to THIS invoice (by index in list)
            invoice_metadata.append((snap_idx, invoice_id, positions))

    return invoices_to_create, invoice_metadata


def _create_publication_position_objects(
    created_invoices: list[OpenCostReportInvoice],
    invoice_metadata: list[tuple[int, int, list[Position]]],
) -> list[OpenCostReportInvoicePosition]:
    """
    Create position objects using created invoice IDs.

    Matches by index - created_invoices[i] corresponds to invoice_metadata[i].
    """
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

    return positions_to_create


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

    # Phase 1: Collect invoices and metadata
    invoices_to_create, invoice_metadata = _collect_publication_invoice_data(
        pub_snapshots, report_publications
    )

    if not invoices_to_create:
        logger.debug("No publication invoices to create")
        return

    # Phase 2: Bulk create invoices
    created_invoices = OpenCostReportInvoice.objects.bulk_create(
        invoices_to_create, batch_size=1000
    )
    logger.debug(f"Created {len(created_invoices)} publication invoices")

    # Phase 3: Create position objects
    positions_to_create = _create_publication_position_objects(created_invoices, invoice_metadata)

    # Phase 4: Bulk create positions
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


def _collect_contract_invoice_data(
    contract_snapshots: list[ContractSnapshotData],
    report_contracts: dict[int, OpenCostReportContract],
) -> tuple[list[OpenCostReportContractInvoice], list[tuple[int, int, list[Position]]]]:
    """
    Collect contract invoice objects ready for bulk creation and track metadata.

    Similar to publication invoices but includes group_id and amount_invoice fields.

    Returns:
        Tuple of (invoices_to_create, invoice_metadata)
        where invoice_metadata is [(snap_idx, invoice_id, positions), ...]
    """
    invoices_to_create = []
    invoice_metadata = []

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

            # Track which positions belong to THIS invoice (by index in list)
            invoice_metadata.append((snap_idx, invoice_id, positions))

    return invoices_to_create, invoice_metadata


def _create_contract_position_objects(
    created_invoices: list[OpenCostReportContractInvoice],
    invoice_metadata: list[tuple[int, int, list[Position]]],
) -> list[OpenCostReportContractInvoicePosition]:
    """
    Create contract position objects using created invoice IDs.

    Matches by index - created_invoices[i] corresponds to invoice_metadata[i].
    """
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

    return positions_to_create


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

    # Phase 1: Collect invoices and metadata
    invoices_to_create, invoice_metadata = _collect_contract_invoice_data(
        contract_snapshots, report_contracts
    )

    if not invoices_to_create:
        logger.debug("No contract invoices to create")
        return

    # Phase 2: Bulk create invoices
    created_invoices = OpenCostReportContractInvoice.objects.bulk_create(
        invoices_to_create, batch_size=1000
    )
    logger.debug(f"Created {len(created_invoices)} contract invoices")

    # Phase 3: Create position objects
    positions_to_create = _create_contract_position_objects(created_invoices, invoice_metadata)

    # Phase 4: Bulk create positions
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


def _store_artifact(
    report: OpenCostReport,
    invoices_in_period: QuerySet[Invoice],
    home_institution_cache: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> None:
    """Store the openCost document, its issue log and the outcome of every report row.

    While the snapshot tables are what the pages read, this second pass over the same data is
    an extra, and an extra is allowed to fail: everything it writes belongs to one savepoint,
    so a failure costs the artifact, says so in the log, and leaves generation - and the
    snapshot the report is shown from - exactly as it was. A half-written artifact is the one
    outcome worse than none, since its rows would claim a document that is not there.
    """
    try:
        with transaction.atomic():
            _write_artifact(report, invoices_in_period, home_institution_cache, institution_cache)
    except Exception:
        logger.exception(
            "openCost artifact could not be stored for report %s; nothing was written",
            report.pk,
        )


def _write_artifact(
    report: OpenCostReport,
    invoices_in_period: QuerySet[Invoice],
    home_institution_cache: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> None:
    """The report's own rows, transformed against live data and written back in one transaction."""
    report_publications = list(report.publications.order_by("id").prefetch_related("invoices"))
    report_contracts = list(report.contracts.order_by("id").prefetch_related("invoices"))
    publication_invoices = [
        report_invoice for row in report_publications for report_invoice in row.invoices.all()
    ]
    contract_invoices = [
        report_invoice for row in report_contracts for report_invoice in row.invoices.all()
    ]
    invoice_ids = {report_invoice.invoice_id for report_invoice in publication_invoices} | {
        report_invoice.invoice_id for report_invoice in contract_invoices
    }

    # The same period-bound positions the report's data was collected from, refetched through
    # the shared fetch so the artifact reads live values rather than the snapshot's copies.
    positions_in_period = Position.objects.filter(invoice__in=invoices_in_period).select_related(
        "invoice", "invoice__creditor"
    )
    live_publications = key_by_id(
        fetch_publications_by_ids(
            {row.publication_id for row in report_publications}, positions=positions_in_period
        )
    )
    live_contracts = key_by_id(
        fetch_contracts_by_ids(
            {row.contract_id for row in report_contracts},
            positions=positions_in_period.filter(contract__isnull=False),
        )
    )
    live_invoices = key_by_id(fetch_invoices_by_ids(invoice_ids))

    transform = transform_report(
        report=report,
        publications=report_publications,
        contracts=report_contracts,
        live_publications=live_publications,
        live_contracts=live_contracts,
        live_invoices=live_invoices,
        home_institution=home_institution_cache,
        institution_cache=institution_cache,
    )

    report.xml_content = "" if transform.data is None else opencost.to_xml(transform.data)
    report.issues = [asdict(warning) for warning in transform.issues]
    # The artifact's log is authoritative for the badge counts, so the columns mirror it
    # in the same save: what the count columns claim is always the log that is stored.
    report.errors_count = sum(1 for w in transform.issues if w.level == "error")
    report.warnings_count = sum(1 for w in transform.issues if w.level == "warning")
    report.save(update_fields=["xml_content", "issues", "errors_count", "warnings_count"])

    _store_publication_outcomes(report_publications, transform.publications)
    _store_contract_outcomes(report_contracts, transform.contracts)
    _store_publication_invoice_outcomes(publication_invoices, transform.publication_invoices)
    _store_contract_invoice_outcomes(contract_invoices, transform.contract_invoices)


def _store_publication_outcomes(
    rows: list[OpenCostReportPublication], outcomes: Mapping[int, ItemOutcome]
) -> None:
    """Record on every publication row whether it reached the document, and where."""
    for row in rows:
        outcome = outcomes[row.publication_id]
        row.exported = outcome.exported
        row.had_errors = outcome.had_errors
        row.xml_ordinal = outcome.xml_ordinal

    OpenCostReportPublication.objects.bulk_update(
        rows, ["exported", "had_errors", "xml_ordinal"], batch_size=500
    )


def _store_contract_outcomes(
    rows: list[OpenCostReportContract], outcomes: Mapping[int, ItemOutcome]
) -> None:
    """Record on every contract row whether it reached the document, and where."""
    for row in rows:
        outcome = outcomes[row.contract_id]
        row.exported = outcome.exported
        row.had_errors = outcome.had_errors
        row.xml_ordinal = outcome.xml_ordinal

    OpenCostReportContract.objects.bulk_update(
        rows, ["exported", "had_errors", "xml_ordinal"], batch_size=500
    )


def _store_publication_invoice_outcomes(
    rows: list[OpenCostReportInvoice], outcomes: Mapping[int, InvoiceOutcome]
) -> None:
    """Record on every publication invoice row whether it reached the document, and at which index."""
    for row in rows:
        outcome = outcomes[row.id]
        row.exported = outcome.exported
        row.had_errors = outcome.had_errors
        row.xml_index = outcome.xml_index

    OpenCostReportInvoice.objects.bulk_update(
        rows, ["exported", "had_errors", "xml_index"], batch_size=500
    )


def _store_contract_invoice_outcomes(
    rows: list[OpenCostReportContractInvoice], outcomes: Mapping[int, InvoiceOutcome]
) -> None:
    """Record on every contract invoice row whether it reached the document, and at which index."""
    for row in rows:
        outcome = outcomes[row.id]
        row.exported = outcome.exported
        row.had_errors = outcome.had_errors
        row.xml_index = outcome.xml_index

    OpenCostReportContractInvoice.objects.bulk_update(
        rows, ["exported", "had_errors", "xml_index"], batch_size=500
    )
