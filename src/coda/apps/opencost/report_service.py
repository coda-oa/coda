"""The report's own item list, and the openCost document that stands for it.

Generation executes the filters once — their result becomes the report's permanent scope — and
records every considered publication, contract and invoice as a membership row before transforming
those rows into the document that gets stored. Regeneration re-runs the same transform over the
stored membership against current CODA data, never consulting the filters again.

The stored document and its issue log are what the read paths serve. Nothing is recomputed per
request, so what a report shows and what downloading it produces cannot drift apart.
"""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from decimal import Decimal
from itertools import chain
from typing import Any

from django.db import transaction
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
    get_invoices_for_period,
    get_publications_for_period,
    key_by_id,
)
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportPublication,
)
from coda.apps.opencost.transformers.live import (
    InvoiceOutcome,
    ItemOutcome,
    get_publisher_and_journal,
    transform_report,
)
from coda.apps.publications.models import Publication
from coda.contexts.exports.dto.filters import ExportFiltersDto

logger = logging.getLogger(__name__)


def generate_report(
    title: str,
    filters: dict[str, Any],
) -> OpenCostReport:
    """Create a report from ``filters``, which are executed here and nowhere else.

    The publications, contracts and invoices the filters reach become the report's membership
    rows — one per item at all three levels — and those rows, not the filters, are the item list
    every later run transforms. How each row fared in this run is recorded beside it.

    An all-excluded report is a normal outcome rather than a failure: it holds no document and an
    issue log that says why, and turns exportable through Regenerate once the data is corrected.
    """
    dto = ExportFiltersDto.model_validate(filters)
    params = dto.to_params()

    if params.date_range is None:
        raise ValueError("date_range is required for generate_report")
    start_date = params.date_range.start
    end_date = params.date_range.end

    logger.info(f"Starting OpenCost report generation: '{title}' ({start_date} to {end_date})")

    report = OpenCostReport.objects.create(
        title=title,
        period_start=start_date,
        period_end=end_date,
        filters=dto.to_storage(),
    )
    logger.debug(f"Created report record: {report.id}")

    logger.info("Fetching publications and contracts...")
    home_institution = build_home_institution_cache()
    invoices_in_period = get_invoices_for_period(
        start_date=start_date,
        end_date=end_date,
        funding_source=params.funding_source,
    )
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
    live_publications = key_by_id(publications)
    live_contracts = key_by_id(contracts)
    institution_cache = build_institution_hierarchy_cache(publications)
    logger.info(f"Fetched {len(live_publications)} publications, {len(live_contracts)} contracts")

    with transaction.atomic():
        publication_rows = _create_publication_rows(report, live_publications)
        contract_rows = _create_contract_rows(report, live_contracts)
        _insert_missing_invoice_links(
            publication_rows, live_publications, contract_rows, live_contracts
        )
        _write_artifact(
            report,
            live_publications,
            live_contracts,
            key_by_id(
                fetch_invoices_by_ids(_pinned_invoice_ids(live_publications, live_contracts))
            ),
            home_institution,
            institution_cache,
        )

    logger.info(
        f"Completed OpenCost report generation: {report.id} "
        f"({len(publication_rows)} publications, {len(contract_rows)} contracts) "
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
    """The document re-run over the report's own rows, inside the locked transaction."""
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

    _insert_missing_invoice_links(
        report_publications, live_publications, report_contracts, live_contracts
    )

    # The home institution is a CODA object like every other: read fresh, never stored.
    home_institution = build_home_institution_cache()
    institution_cache = build_institution_hierarchy_cache(live_publications_qs)

    _write_artifact(
        report,
        live_publications,
        live_contracts,
        key_by_id(fetch_invoices_by_ids(invoice_ids)),
        home_institution,
        institution_cache,
    )


def _create_publication_rows(
    report: OpenCostReport, live_publications: Mapping[int, Publication]
) -> list[OpenCostReportPublication]:
    """One membership row per considered publication, in entity id order.

    ``title`` and ``publisher`` are the two values an exported publication's own document entry
    cannot state - a DOI-bearing entry names neither - so they are kept here for the detail table.
    Everything the document does state is read live on every run, so the row says only that this
    publication is one of the report's items; how the run went is written once the document exists.
    """
    rows = [
        OpenCostReportPublication(
            report=report,
            publication_id=publication_id,
            title=live_publications[publication_id].title,
            publisher=get_publisher_and_journal(live_publications[publication_id])[0],
        )
        for publication_id in sorted(live_publications)
    ]

    created = OpenCostReportPublication.objects.bulk_create(rows, batch_size=1000)
    logger.debug(f"Created {len(created)} report publications")
    return created


def _create_contract_rows(
    report: OpenCostReport, live_contracts: Mapping[int, Contract]
) -> list[OpenCostReportContract]:
    """One membership row per considered contract, in entity id order.

    ``contract_name`` is what an excluded contract gets reported and displayed under, and an
    excluded contract has no document entry to read a name from - so the row keeps the name. The
    rest of a contract's exported content is read live on every run.
    """
    rows = [
        OpenCostReportContract(
            report=report,
            contract_id=contract_id,
            contract_name=live_contracts[contract_id].name,
        )
        for contract_id in sorted(live_contracts)
    ]

    created = OpenCostReportContract.objects.bulk_create(rows, batch_size=1000)
    logger.debug(f"Created {len(created)} report contracts")
    return created


def _insert_missing_invoice_links(
    report_publications: list[OpenCostReportPublication],
    live_publications: Mapping[int, Publication],
    report_contracts: list[OpenCostReportContract],
    live_contracts: Mapping[int, Contract],
) -> None:
    """Create the parent-invoice link rows that live positions imply but the tables lack.

    An invoice is one of the report's items when a position of the parent sits on it, which at
    generation is the whole third level and on a later run is the link a fix inside a pinned
    invoice created. Without the row the transform would never see that cost: it walks an item's
    invoices through these rows and only reads the positions to say what an invoice is being
    given. Item scope is untouched either way - both levels of every inserted row already exist -
    and the unique pair keeps repeated passes idempotent.
    """
    existing_publication_links = set(
        OpenCostReportInvoice.objects.filter(
            report_publication__in=report_publications
        ).values_list("report_publication_id", "invoice_id")
    )
    publication_links = [
        OpenCostReportInvoice(report_publication_id=row.id, invoice_id=invoice_id)
        for row in report_publications
        for invoice_id in sorted(_positions_by_invoice(live_publications[row.publication_id]))
        if (row.id, invoice_id) not in existing_publication_links
    ]
    OpenCostReportInvoice.objects.bulk_create(publication_links)

    existing_contract_links = set(
        OpenCostReportContractInvoice.objects.filter(
            report_contract__in=report_contracts
        ).values_list("report_contract_id", "invoice_id")
    )
    contract_links: list[OpenCostReportContractInvoice] = []
    for row in report_contracts:
        positions_by_invoice = _positions_by_invoice(live_contracts[row.contract_id])
        for invoice_id in sorted(positions_by_invoice):
            if (row.id, invoice_id) in existing_contract_links:
                continue

            positions = positions_by_invoice[invoice_id]
            contract_links.append(
                OpenCostReportContractInvoice(
                    report_contract_id=row.id,
                    invoice_id=invoice_id,
                    amount_invoice=sum(
                        (position.cost_amount for position in positions), Decimal(0)
                    ),
                    amount_invoice_currency=positions[0].cost_currency,
                )
            )
    OpenCostReportContractInvoice.objects.bulk_create(contract_links)


def _positions_by_invoice(entity: Publication | Contract) -> dict[int, list[Position]]:
    """The entity's live positions grouped by the invoice they sit on, in fetched order.

    The groups' order is the order this item's invoices are recorded in, which is the order the
    document lists them in - so the invoice order comes from the report's own rows rather than
    from whatever order a query happens to answer in.
    """
    grouped: dict[int, list[Position]] = {}
    for position in entity.position_set.all():
        grouped.setdefault(position.invoice_id, []).append(position)

    return grouped


def _pinned_invoice_ids(
    live_publications: Mapping[int, Publication],
    live_contracts: Mapping[int, Contract],
) -> set[int]:
    """The invoices the fetched items hold a position on.

    These are exactly the invoices the link rows name, since the rows are created from the same
    positions - so the transform never meets a row pointing at an invoice it was not given.
    """
    publication_positions: Iterable[Position] = chain.from_iterable(
        publication.position_set.all() for publication in live_publications.values()
    )
    contract_positions: Iterable[Position] = chain.from_iterable(
        contract.position_set.all() for contract in live_contracts.values()
    )

    return {position.invoice_id for position in chain(publication_positions, contract_positions)}


def _write_artifact(
    report: OpenCostReport,
    live_publications: Mapping[int, Publication],
    live_contracts: Mapping[int, Contract],
    live_invoices: Mapping[int, Invoice],
    home_institution: HomeInstitutionCache,
    institution_cache: InstitutionHierarchyCache,
) -> None:
    """The report's own rows, transformed against live data and written back in one save.

    The rows are read here, after the link pass has run, so every item reaches the transform
    holding each invoice a live position implies. Document, issue log and row outcomes are written
    together inside the caller's transaction: a run that fails partway leaves no document that
    only some of the rows claim.
    """
    report_publications = list(report.publications.order_by("id").prefetch_related("invoices"))
    report_contracts = list(report.contracts.order_by("id").prefetch_related("invoices"))
    publication_invoices = [
        report_invoice for row in report_publications for report_invoice in row.invoices.all()
    ]
    contract_invoices = [
        report_invoice for row in report_contracts for report_invoice in row.invoices.all()
    ]

    transform = transform_report(
        report=report,
        publications=report_publications,
        contracts=report_contracts,
        live_publications=live_publications,
        live_contracts=live_contracts,
        live_invoices=live_invoices,
        home_institution=home_institution,
        institution_cache=institution_cache,
    )

    report.xml_content = "" if transform.data is None else opencost.to_xml(transform.data)
    report.issues = [asdict(warning) for warning in transform.issues]
    # The stored issue log is the counts' source for the read paths, so the two are written
    # together: a run that clears the log must also clear the columns, or the union count
    # properties - and every badge - keep answering from the run that produced the old log.
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
