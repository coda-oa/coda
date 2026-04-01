from io import BytesIO, StringIO
from typing import Any
from datetime import datetime
from django.db.models import QuerySet
from django.db import transaction
from django.utils import timezone
import secrets

import polars as pl

from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.domain.institution.links import create_link
from coda.apps.invoices.models import FundingSource
from coda.apps.preferences.models import GlobalPreferences

from dataclasses import dataclass, field

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import Invoice


def generate_internal_id() -> str:
    random_part = secrets.token_urlsafe(6)
    return f"inst_{random_part[:8]}"


@dataclass
class ImportError:
    institution_name: str
    message: str


@dataclass
class ImportResult:
    total: int = 0
    fully_imported: int = 0
    partially_imported: int = 0
    matched_by_internal_id: int = 0
    matched_by_identifier: int = 0
    created_new: int = 0
    errors: list[ImportError] = field(default_factory=list)


def import_from_file(file: BytesIO | StringIO) -> ImportResult:
    df = pl.read_csv(file, separator=";", has_header=True)

    result = ImportResult()

    link_types = {lt.name: lt for lt in InstitutionLinkType.objects.all()}

    institutions = _match_or_create_institutions(df, result)

    for i, institution in enumerate(institutions):
        result.total += 1
        had_errors = False

        row = df.row(i, named=True)

        _handle_affiliation(institution, row)
        _handle_archived_status(institution, row)

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
    parent_value = row.get("parent")
    if not parent_value:
        return

    parent_id = str(parent_value).strip()
    if not parent_id:
        return

    parent = Institution.all_objects.filter(internal_id=parent_id).first()
    if parent:
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
            link_type = link_types[link_type_name]
            institution.links.filter(type=link_type).delete()
            institution.links.create(type=link_type, value=link.value())
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


def _handle_archived_status(institution: Institution, row: dict[str, Any]) -> None:
    archived_value = row.get("archived")
    if archived_value is not None:
        archived_str = str(archived_value).strip().lower()
        if archived_str == "true":
            if not institution.archived_at:
                institution.archived_at = timezone.now()
        elif archived_str == "false":
            institution.archived_at = None


def _match_by_internal_id(row: dict[str, Any]) -> Institution | None:
    internal_id = row.get("internal_id")
    if not internal_id:
        return None

    internal_id = str(internal_id).strip()
    if not internal_id:
        return None

    institution = Institution.all_objects.filter(internal_id=internal_id).first()
    if institution:
        institution.name = str(row.get("name"))

    return institution


def _match_by_external_identifier(row: dict[str, Any]) -> Institution | None:
    for id_type in ["ROR", "ISNI", "Ringgold"]:
        id_value = row.get(id_type)
        if not id_value:
            continue

        id_value = str(id_value).strip()
        if not id_value:
            continue

        institution = Institution.all_objects.filter(
            links__type__name=id_type, links__value=id_value
        ).first()

        if institution:
            institution.name = str(row.get("name"))
            return institution

    return None


def _get_or_create_by_name(row: dict[str, Any]) -> Institution:
    name = row.get("name")
    institution, _ = Institution.all_objects.get_or_create(name=name)
    return institution


def _set_internal_id_if_needed(institution: Institution, row: dict[str, Any]) -> None:
    internal_id = row.get("internal_id")
    if internal_id:
        internal_id = str(internal_id).strip()
        if internal_id and not institution.internal_id:
            institution.internal_id = internal_id


def _match_or_create_institutions(df: pl.DataFrame, result: ImportResult) -> list[Institution]:
    institutions = []
    for i in range(len(df)):
        row = df.row(i, named=True)

        institution = _match_by_internal_id(row)
        if institution:
            result.matched_by_internal_id += 1
        else:
            institution = _match_by_external_identifier(row)
            if institution:
                result.matched_by_identifier += 1
            else:
                institution = _get_or_create_by_name(row)
                result.created_new += 1

        _set_internal_id_if_needed(institution, row)
        institutions.append(institution)

    return institutions


def can_delete_institution(institution: Institution) -> tuple[bool, list[str]]:
    blocking: list[str] = []

    check_child_institutions(institution, blocking)
    check_author_affiliations(institution, blocking)
    check_funding_sources(institution, blocking)
    check_institution_links(institution, blocking)
    check_home_institution(institution, blocking)

    can_delete = len(blocking) == 0
    return can_delete, blocking


def check_home_institution(institution: Institution, blocking: list[str]) -> None:
    if GlobalPreferences.objects.filter(home_institution=institution).exists():
        blocking.append("set as home institution in preferences")


def check_institution_links(institution: Institution, blocking: list[str]) -> None:
    if institution.links.exists():
        blocking.append(f"{institution.links.count()} identifier(s)/link(s)")


def check_funding_sources(institution: Institution, blocking: list[str]) -> None:
    funding_sources = FundingSource.objects.filter(institution=institution)
    # Only count funding sources that are actually being used
    used_funding_sources = funding_sources.filter(funding_assignments__isnull=False).distinct()
    if used_funding_sources.exists():
        blocking.append(f"{used_funding_sources.count()} active funding source(s)")


def check_author_affiliations(institution: Institution, blocking: list[str]) -> None:
    if hasattr(institution, "affiliated_authors"):
        authors_count = institution.affiliated_authors.count()
        if authors_count > 0:
            blocking.append(f"{authors_count} author affiliation(s)")


def check_child_institutions(institution: Institution, blocking: list[str]) -> None:
    if institution.children.exists():
        blocking.append(f"{institution.children.count()} child institution(s)")


def archive(institution: Institution, replacement: Institution | None = None) -> None:
    if _is_home_institution(institution) and replacement is None:
        raise ValueError("Cannot archive home institution without replacement")

    if institution.archived_at is not None:
        raise ValueError("Institution is already archived")

    if replacement is not None:
        institution.children.update(parent=replacement)
        _update_home_institution_if_needed(institution, replacement)

    timestamp = timezone.now()
    _archive_institution_tree(institution, timestamp)


def _archive_institution_tree(institution: Institution, timestamp: datetime) -> None:
    for child in institution.children.all():
        _archive_institution_tree(child, timestamp)

    if institution.archived_at is None:
        institution.archived_at = timestamp
        institution.virtual = True
        institution.save()


def restore_without_children(
    institution: Institution, new_parent: Institution | None = None
) -> None:
    institution.archived_at = None
    institution.virtual = False
    if new_parent is not None:
        institution.parent = new_parent
    institution.save()


def restore_with_children(institution: Institution, new_parent: Institution | None = None) -> None:
    if new_parent is not None:
        institution.parent = new_parent
        institution.save()
    _restore_institution_tree(institution)


def _restore_institution_tree(institution: Institution) -> None:
    if institution.archived_at is not None:
        institution.archived_at = None
        institution.virtual = False
        institution.save()

    for child in Institution.all_objects.filter(parent=institution):
        _restore_institution_tree(child)


def _is_home_institution(institution: Institution) -> bool:
    return GlobalPreferences.objects.filter(home_institution=institution).exists()


def _update_home_institution_if_needed(institution: Institution, successor: Institution) -> None:
    try:
        preferences = GlobalPreferences.objects.get(home_institution=institution)
        preferences.home_institution = successor
        preferences.save()
    except GlobalPreferences.DoesNotExist:
        pass


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
    children = Institution.all_objects.filter(parent=institution)

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


def _ensure_all_institutions_have_internal_ids(
    institutions: QuerySet[Institution],
) -> dict[int, str]:
    id_mapping = {}
    for inst in institutions:
        if not inst.internal_id:
            inst.internal_id = generate_internal_id()
            inst.save()
        assert inst.internal_id is not None  # For mypy: always set at this point
        id_mapping[inst.pk] = inst.internal_id
    return id_mapping


def _extract_external_identifiers(institution: Institution) -> dict[str, str]:
    identifiers = {"ROR": "", "ISNI": "", "Ringgold": ""}

    for link in institution.links.all():
        if link.type.name in identifiers:
            identifiers[link.type.name] = link.value

    return identifiers


def _institution_to_csv_row(inst: Institution, id_mapping: dict[int, str]) -> dict[str, str]:
    parent_id = ""
    if inst.parent_id:
        parent_id = id_mapping.get(inst.parent_id, "")

    usable_affiliation = "false" if inst.virtual else "true"
    archived = "true" if inst.archived_at else "false"

    identifiers = _extract_external_identifiers(inst)

    return {
        "internal_id": id_mapping[inst.pk],
        "name": inst.name,
        "parent": parent_id,
        "usableAffiliation": usable_affiliation,
        "archived": archived,
        "ROR": identifiers["ROR"],
        "ISNI": identifiers["ISNI"],
        "Ringgold": identifiers["Ringgold"],
    }


def export_to_csv() -> str:
    institutions = Institution.all_objects.select_related("parent").prefetch_related("links").all()

    with transaction.atomic():
        id_mapping = _ensure_all_institutions_have_internal_ids(institutions)
        rows = [_institution_to_csv_row(inst, id_mapping) for inst in institutions]

    df = pl.DataFrame(rows)
    csv_buffer = StringIO()
    df.write_csv(csv_buffer, separator=";")

    return csv_buffer.getvalue()
