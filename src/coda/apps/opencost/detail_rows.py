"""Detail-table rows for one report: seed rows joined onto its stored document.

Pure assembly, no HTTP concerns — ``views.report_detail`` fetches the report and renders
what :func:`build_detail_rows` returns.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import opencost
from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportPublication,
)
from opencost import Data

logger = logging.getLogger(__name__)


class DetailPublication(NamedTuple):
    """One publication row of the detail table: seed columns joined onto the stored document."""

    seed: OpenCostReportPublication
    fundingrequest_id: int | None
    title: str  # the seed column: a DOI-bearing publication names no title in the XML
    publisher: str  # the seed column, same reason
    doi: str
    publication_type: str
    contract_esac: str
    external_costsplitting: bool | None
    invoice_count: int
    status: str  # "clean" | "degraded" | "excluded"
    reasons: str  # error-level issue messages naming this entity


class DetailContract(NamedTuple):
    """One contract row of the detail table, joined the same way."""

    seed: OpenCostReportContract
    contract_id: int
    name: str
    esac: str
    institution_name: str
    participation_from: str
    participation_to: str
    invoice_count: int
    status: str
    reasons: str


class DetailRows(NamedTuple):
    """Both detail tables of one report, in page order."""

    publications: list[DetailPublication]
    contracts: list[DetailContract]


def build_detail_rows(report: OpenCostReport) -> DetailRows:
    """The report's publication and contract rows as the detail table shows them.

    The stored document is the row data's source; an all-excluded report legitimately has
    none, in which case the seed rows and the issue log carry the table. Expects
    ``report.publications``/``report.contracts`` to be prefetched by the caller — the page
    queries them once.
    """
    document = _stored_document(report)
    error_issues = _error_issues_by_entity(report)

    publications = [
        _publication_detail(
            row, document, _issues_for(error_issues, "publication", row.publication_id)
        )
        for row in report.publications.all()
    ]
    contracts = [
        _contract_detail(row, document, _issues_for(error_issues, "contract", row.contract_id))
        for row in report.contracts.all()
    ]
    return DetailRows(publications=publications, contracts=contracts)


def _stored_document(report: OpenCostReport) -> Data | None:
    """The stored XML as models - None when there is none or it no longer parses.

    Empty content is not a failure: a report whose every item was excluded has no document,
    and from_xml would raise on the empty string. A document that cannot be parsed degrades
    every exported row to its issue entry instead of failing the page.
    """
    if not report.xml_content:
        return None
    try:
        return opencost.from_xml(report.xml_content)
    except Exception:
        logger.exception("Stored openCost XML of report %s could not be parsed", report.pk)
        return None


def _error_issues_by_entity(report: OpenCostReport) -> dict[int, list[dict[str, Any]]]:
    """The stored issue log grouped by the entity each error names, for the detail-row join.

    Grouping is on ``entity_id`` alone; whether an issue belongs to a given row is decided
    per row by ``_issues_for``, since ids collide across CODA tables. ``global`` issues -
    exclusions caused by the institution settings - keep the identity of the item they
    were reported on, so they join onto that item's row too.
    """
    grouped: dict[int, list[dict[str, Any]]] = {}
    for issue in report.issues or []:
        entity_id = issue.get("entity_id")
        if issue.get("level") == "error" and entity_id is not None:
            grouped.setdefault(int(entity_id), []).append(issue)
    return grouped


def _issues_for(
    grouped: Mapping[int, list[dict[str, Any]]], entity_type: str, entity_id: int
) -> list[dict[str, Any]]:
    """The error issues naming one detail row.

    Entity ids are only unique per CODA table, so the stored entity type must match too:
    a publication and a contract can share an id, and one's exclusion reason must not
    decorate the other's row. Global institution exclusions are reported under the
    identity of the item they name - type "global", that item's own id - so they join
    onto that row as well.
    """
    return [
        issue
        for issue in grouped.get(entity_id, [])
        if issue.get("entity_type") in (entity_type, "global")
    ]


def _publication_detail(
    row: OpenCostReportPublication,
    document: Data | None,
    issues: list[dict[str, Any]],
) -> DetailPublication:
    """The row as the table shows it: from the XML entry the ordinal names, else from issues."""
    reasons = "; ".join(str(issue.get("message", "")) for issue in issues)
    element = _entry_at(document.publication if document else None, row)
    if element is None:
        # Excluded - or exported by the flags yet named no entry the document holds; either
        # way the row falls back to its issue log and the kept seed columns.
        return DetailPublication(
            seed=row,
            fundingrequest_id=_fundingrequest_id(row),
            title=row.title,
            publisher=row.publisher,
            doi="",
            publication_type="",
            contract_esac="",
            external_costsplitting=None,
            invoice_count=0,
            status="excluded",
            reasons=reasons,
        )

    part_of_contract = element.cost_data.part_of_contract
    return DetailPublication(
        seed=row,
        fundingrequest_id=_fundingrequest_id(row),
        title=row.title,
        publisher=row.publisher,
        doi=element.primary_identifier.doi or "",
        publication_type=element.publication_type.value if element.publication_type else "",
        contract_esac=(part_of_contract.primary_identifier.value if part_of_contract else ""),
        external_costsplitting=element.external_costsplitting,
        invoice_count=len(element.cost_data.invoice or []),
        status="degraded" if row.had_errors else "clean",
        reasons=reasons,
    )


def _contract_detail(
    row: OpenCostReportContract,
    document: Data | None,
    issues: list[dict[str, Any]],
) -> DetailContract:
    """The row as the table shows it: from the XML entry the ordinal names, else from issues."""
    reasons = "; ".join(str(issue.get("message", "")) for issue in issues)
    element = _entry_at(document.contract if document else None, row)
    if element is None:
        name = str(issues[0].get("entity_name") or "") if issues else ""
        return DetailContract(
            seed=row,
            contract_id=row.contract_id,
            name=name or row.contract.name,
            esac="",
            institution_name="",
            participation_from="",
            participation_to="",
            invoice_count=0,
            status="excluded",
            reasons=reasons,
        )

    names = element.institution.name if element.institution else None
    invoice_groups = element.cost_data.invoice_group
    return DetailContract(
        seed=row,
        contract_id=row.contract_id,
        name=element.contract_name,
        esac=element.primary_identifier.value,
        institution_name=names[0].value if names else "",
        participation_from=element.participation.from_ or "",
        participation_to=element.participation.to or "",
        invoice_count=len(invoice_groups[0].invoice or []) if invoice_groups else 0,
        status="degraded" if row.had_errors else "clean",
        reasons=reasons,
    )


def _entry_at[T](
    entries: Sequence[T] | None, row: OpenCostReportPublication | OpenCostReportContract
) -> T | None:
    """The document entry a seed row's ordinal names; None when it names none.

    Defensive by design: a regenerate racing between the report and the seed-row queries can
    leave an ordinal the freshly parsed document does not have. That row degrades to its
    issue entry; the page never fails over it.
    """
    if entries is None or not row.exported or row.xml_ordinal is None:
        return None
    if not 0 <= row.xml_ordinal < len(entries):
        return None
    return entries[row.xml_ordinal]


def _fundingrequest_id(row: OpenCostReportPublication) -> int | None:
    """The request the publication was filed under, when it was filed at all."""
    fundingrequest = getattr(row.publication, "fundingrequest", None)
    return None if fundingrequest is None else int(fundingrequest.id)
