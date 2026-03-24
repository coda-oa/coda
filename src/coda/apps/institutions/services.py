from io import BytesIO, StringIO
from typing import Any
from django.db.models import QuerySet
from django.utils import timezone

import polars as pl

from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.domain.institution.links import create_link
from coda.apps.invoices.models import FundingSource

from dataclasses import dataclass, field

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice


@dataclass
class ImportError:
    institution_name: str
    message: str


@dataclass
class ImportResult:
    total: int = 0
    fully_imported: int = 0
    partially_imported: int = 0
    errors: list[ImportError] = field(default_factory=list)


def import_from_file(file: BytesIO | StringIO) -> ImportResult:
    df = pl.read_csv(file, separator=";", has_header=True)

    result = ImportResult()

    link_types = {lt.name: lt for lt in InstitutionLinkType.objects.all()}

    institutions = _match_or_create_institutions(df)

    for i, institution in enumerate(institutions):
        result.total += 1
        had_errors = False

        row = df.row(i, named=True)

        _handle_affiliation(institution, row)

        _link_parent_institution(df, institution, row)

        institution.save()

        had_errors = _handle_identifiers(result, link_types, institution, row)

        if had_errors:
            result.partially_imported += 1
        else:
            result.fully_imported += 1

    return result


def _link_parent_institution(
    df: pl.DataFrame, institution: Institution, row: dict[str, Any]
) -> None:
    parent_row_number_in_file = row.get("parent")
    if parent_row_number_in_file is not None:
        parent_name: str = _parent_row(df, parent_row_number_in_file).get("name", "")
        parent = Institution.objects.get(name=parent_name)
        institution.parent = parent


def _handle_identifiers(
    result: ImportResult,
    link_types: dict[str, InstitutionLinkType],
    institution: Institution,
    row: dict[str, Any],
) -> bool:
    had_errors = False
    for link_type_name in ["ROR", "ISNI", "Ringgold"]:
        value = row.get(link_type_name)

        if not value or link_type_name not in link_types:
            continue

        value = str(value)

        try:
            link = create_link(link_type_name, value)
            institution.links.get_or_create(type=link_types[link_type_name], value=link.value())
        except Exception as e:
            had_errors = True
            result.errors.append(
                ImportError(
                    institution_name=institution.name, message=f"{link_type_name}: {str(e)}"
                )
            )

    return had_errors


def _handle_affiliation(institution: Institution, row: dict[str, Any]) -> None:
    affiliation_value = row.get("usableAffiliation")
    if affiliation_value is not None:
        affiliation_str = str(affiliation_value).strip().lower()
        if affiliation_str == "true":
            institution.virtual = False
        elif affiliation_str == "false":
            institution.virtual = True
        elif affiliation_str == "":
            institution.virtual = False


def _match_or_create_institutions(df: pl.DataFrame) -> list[Institution]:
    institutions = []
    for i in range(len(df)):
        row = df.row(i, named=True)
        name = row.get("name")

        institution = None
        for id_type in ["ROR", "ISNI", "Ringgold"]:
            id_value = row.get(id_type)
            if id_value:
                id_value = str(id_value).strip()
                existing = Institution.objects.filter(
                    links__type__name=id_type, links__value=id_value
                ).first()
                if existing:
                    institution = existing
                    institution.name = str(name)
                    break

        if not institution:
            institution, _ = Institution.objects.get_or_create(name=name)

        institutions.append(institution)

    return institutions


def _parent_row(df: pl.DataFrame, parent_row_number_in_file: int) -> dict[str, Any]:
    return df.row(_parent_row_number(parent_row_number_in_file), named=True)


# NOTE: HEADER_OFFSET is 2 because the first row is the header and we start counting numbers from 0 after the header
HEADER_OFFSET = 2


def _parent_row_number(parent_row_number_in_file: int) -> int:
    return parent_row_number_in_file - HEADER_OFFSET


def can_delete_institution(institution: Institution) -> tuple[bool, list[str]]:
    blocking: list[str] = []

    check_child_institutions(institution, blocking)
    check_author_affiliations(institution, blocking)
    check_funding_sources(institution, blocking)
    check_institution_links(institution, blocking)

    can_delete = len(blocking) == 0
    return can_delete, blocking


def check_institution_links(institution: Institution, blocking: list[str]) -> None:
    if institution.links.exists():
        blocking.append(f"{institution.links.count()} identifiers/links")


def check_funding_sources(institution: Institution, blocking: list[str]) -> None:
    funding_sources = FundingSource.objects.filter(institution=institution)
    if funding_sources.exists():
        blocking.append(f"{funding_sources.count()} funding sources")


def check_author_affiliations(institution: Institution, blocking: list[str]) -> None:
    if hasattr(institution, "affiliated_authors"):
        authors_count = institution.affiliated_authors.count()
        if authors_count > 0:
            blocking.append(f"{authors_count} author affiliations")


def check_child_institutions(institution: Institution, blocking: list[str]) -> None:
    if institution.children.exists():
        blocking.append(f"{institution.children.count()} child institutions")


def archive_and_create_successor(institution: Institution, successor_name: str) -> Institution:
    if institution.archived_at is not None:
        raise ValueError("Institution is already archived")

    successor = Institution.objects.create(name=successor_name)

    institution.archived_at = timezone.now()
    institution.succeeded_by.add(successor)
    institution.save()

    return successor


def archive_with_existing_successor(
    institution: Institution, successors: list[Institution]
) -> None:
    if institution.archived_at is not None:
        raise ValueError("Institution is already archived")

    if not successors:
        raise ValueError("Must provide at least one successor institution")

    institution.archived_at = timezone.now()
    institution.succeeded_by.add(*successors)
    institution.save()


@dataclass
class InstitutionRelationships:
    children: QuerySet[Institution]
    funding_requests: QuerySet[FundingRequest]
    invoices: QuerySet[Invoice]
    links: QuerySet[InstitutionLink]

    @property
    def has_any(self) -> bool:
        return (
            self.children.exists()
            or self.funding_requests.exists()
            or self.invoices.exists()
            or self.links.exists()
        )


def get_institution_relationships(institution: Institution) -> InstitutionRelationships:
    children = institution.children.all()

    funding_requests = FundingRequest.objects.filter(
        publication__relevant_authors__affiliation=institution
    ).distinct()

    funding_sources = FundingSource.objects.filter(institution=institution)
    if funding_sources.exists():
        invoices = Invoice.objects.filter(
            positions__funding_assignments__funding_source__in=funding_sources
        ).distinct()
    else:
        invoices = Invoice.objects.none()

    links = institution.links.all()

    return InstitutionRelationships(
        children=children,
        funding_requests=funding_requests,
        invoices=invoices,
        links=links,
    )
