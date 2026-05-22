import secrets
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from typing import Any

import polars as pl
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution, InstitutionLink, InstitutionLinkType
from coda.apps.invoices.models import FundingSource, Invoice
from coda.apps.preferences.models import GlobalPreferences
from coda.domain.institution.links import create_link

# Constants
BULK_OPERATION_BATCH_SIZE = 100
IDENTIFIER_TYPES = ["ROR", "ISNI", "Ringgold"]


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

    # Bulk create new institutions first to ensure all have PKs
    _bulk_create_new_institutions(institutions)

    # Build lookup table for parent relationships (now all institutions have PKs)
    internal_id_lookup = _build_internal_id_lookup(institutions)

    # First pass: set properties and relationships
    links_to_delete, links_to_create = _process_properties_and_relationships(
        df, institutions, link_types, internal_id_lookup, result
    )

    # Second pass: validate and apply archived status
    parent_children_map = _build_parent_children_map(institutions)
    _process_archive_status(df, institutions, parent_children_map, result)

    # Bulk persist all changes
    _bulk_save_all_changes(institutions, links_to_delete, links_to_create)

    return result


def _build_internal_id_lookup(institutions: list[Institution]) -> dict[str, Institution]:
    """Build a lookup table mapping internal_id to Institution for fast parent lookups."""
    # Start with institutions from the import
    lookup = {inst.internal_id: inst for inst in institutions if inst.internal_id}

    # Also fetch all existing institutions with internal_ids to handle parents not in the CSV
    # Collect all internal_ids we need to look up
    internal_ids_in_import = set(lookup.keys())

    # Get all institutions from DB that have internal_ids but aren't in our current batch
    existing_institutions = Institution.all_objects.filter(internal_id__isnull=False).exclude(
        internal_id__in=internal_ids_in_import
    )

    # Add them to the lookup
    for inst in existing_institutions:
        if inst.internal_id:
            lookup[inst.internal_id] = inst

    return lookup


def _bulk_create_new_institutions(institutions: list[Institution]) -> None:
    """Create new institutions in database to ensure all have primary keys."""
    new_institutions = [inst for inst in institutions if not inst.pk]
    if new_institutions:
        Institution.all_objects.bulk_create(new_institutions, batch_size=BULK_OPERATION_BATCH_SIZE)


def _process_properties_and_relationships(
    df: pl.DataFrame,
    institutions: list[Institution],
    link_types: dict[str, InstitutionLinkType],
    internal_id_lookup: dict[str, Institution],
    result: ImportResult,
) -> tuple[list[int], list[InstitutionLink]]:
    """Process all institution properties and relationships. Returns link operations."""
    links_to_delete: list[int] = []
    links_to_create: list[InstitutionLink] = []

    for i, institution in enumerate(institutions):
        result.total += 1
        row = df.row(i, named=True)

        _apply_affiliation(institution, row)
        _apply_parent_relationship(institution, row, internal_id_lookup, result)

        had_errors = _collect_identifier_operations(
            result, link_types, institution, row, links_to_delete, links_to_create
        )

        if had_errors:
            result.partially_imported += 1
        else:
            result.fully_imported += 1

    return links_to_delete, links_to_create


def _process_archive_status(
    df: pl.DataFrame,
    institutions: list[Institution],
    parent_children_map: dict[int, list[Institution]],
    result: ImportResult,
) -> None:
    """Process archive status with validation for all institutions."""
    institutions_to_archive = _build_archive_intent_map(df, institutions)

    for i, institution in enumerate(institutions):
        row = df.row(i, named=True)
        had_archive_error = _apply_archived_status_with_validation(
            institution, row, institutions_to_archive, parent_children_map, result
        )

        if had_archive_error:
            _adjust_import_counts_for_error(result)


def _adjust_import_counts_for_error(result: ImportResult) -> None:
    """Adjust import counts when an archive validation error occurs."""
    if result.fully_imported > 0:
        result.fully_imported -= 1
        result.partially_imported += 1


def _bulk_save_all_changes(
    institutions: list[Institution],
    links_to_delete: list[int],
    links_to_create: list[InstitutionLink],
) -> None:
    """Persist all changes to database in bulk operations."""
    if institutions:
        Institution.all_objects.bulk_update(
            institutions,
            fields=["internal_id", "name", "parent", "virtual", "archived_at"],
            batch_size=BULK_OPERATION_BATCH_SIZE,
        )

    if links_to_delete:
        InstitutionLink.objects.filter(id__in=links_to_delete).delete()

    if links_to_create:
        InstitutionLink.objects.bulk_create(links_to_create, batch_size=BULK_OPERATION_BATCH_SIZE)


def _build_parent_children_map(
    institutions: list[Institution],
) -> dict[int, list[Institution]]:
    """Build a map of parent_id -> list of children for validation without DB queries."""
    parent_children_map: dict[int, list[Institution]] = {}

    # Add children from the import batch
    for institution in institutions:
        if institution.parent_id:
            _add_child_to_map(parent_children_map, institution.parent_id, institution)

    # Fetch ALL existing children in a single query
    institution_pks = {inst.pk for inst in institutions if inst.pk}
    parent_pks = [inst.pk for inst in institutions if inst.pk]

    if parent_pks:
        # Get all existing children whose parents are in the import batch,
        # but exclude children that are also in the import batch
        existing_children = Institution.all_objects.filter(parent_id__in=parent_pks).exclude(
            pk__in=institution_pks
        )

        # Group them by parent_id
        for child in existing_children:
            if child.parent_id is not None:
                _add_child_to_map(parent_children_map, child.parent_id, child)

    return parent_children_map


def _add_child_to_map(
    parent_children_map: dict[int, list[Institution]], parent_id: int, child: Institution
) -> None:
    """Add a child institution to the parent-children map."""
    if parent_id not in parent_children_map:
        parent_children_map[parent_id] = []
    parent_children_map[parent_id].append(child)


def _apply_parent_relationship(
    institution: Institution,
    row: dict[str, Any],
    internal_id_lookup: dict[str, Institution],
    result: ImportResult,
) -> None:
    """Set institution's parent based on parent internal_id in CSV."""
    parent_value = row.get("parent")
    if not parent_value:
        return

    parent_id = str(parent_value).strip()
    if not parent_id:
        return

    parent = internal_id_lookup.get(parent_id)
    if parent:
        if parent.pk == institution.pk or parent.is_descendant_of(institution):
            result.errors.append(
                ImportError(
                    institution_name=institution.name,
                    message="Cannot set parent: it would create a cycle in the institution hierarchy.",
                )
            )
            return
        institution.set_parent(parent)


def _collect_identifier_operations(
    result: ImportResult,
    link_types: dict[str, InstitutionLinkType],
    institution: Institution,
    row: dict[str, Any],
    links_to_delete: list[int],
    links_to_create: list[InstitutionLink],
) -> bool:
    """Collect link operations to be executed later in bulk."""
    had_errors = False

    for link_type_name in IDENTIFIER_TYPES:
        value = row.get(link_type_name)
        if not value or link_type_name not in link_types:
            continue

        try:
            _create_identifier_link(
                institution,
                link_type_name,
                str(value),
                link_types,
                links_to_delete,
                links_to_create,
            )
        except Exception as e:
            had_errors = True
            result.errors.append(
                ImportError(
                    institution_name=institution.name, message=f"{link_type_name}: {str(e)}"
                )
            )

    return had_errors


def _create_identifier_link(
    institution: Institution,
    link_type_name: str,
    value: str,
    link_types: dict[str, InstitutionLinkType],
    links_to_delete: list[int],
    links_to_create: list[InstitutionLink],
) -> None:
    """Create an identifier link. Raises exception on validation error."""
    link = create_link(link_type_name, value)
    link_type = link_types[link_type_name]

    # Collect existing links to delete
    existing_links = institution.links.filter(type=link_type)
    links_to_delete.extend(existing_links.values_list("id", flat=True))

    # Create new link object (not saved yet)
    links_to_create.append(
        InstitutionLink(institution=institution, type=link_type, value=link.value())
    )


def _apply_affiliation(institution: Institution, row: dict[str, Any]) -> None:
    """Set institution's virtual field based on usableAffiliation column."""
    affiliation_value = row.get("usableAffiliation")
    if affiliation_value is None:
        return

    affiliation_str = str(affiliation_value).strip().lower()
    # "true" or "" means usable (not virtual), "false" means virtual
    institution.virtual = affiliation_str == "false"


def _build_archive_intent_map(df: pl.DataFrame, institutions: list[Institution]) -> set[int]:
    """Build a set of institution PKs that should be archived according to the CSV."""
    institutions_to_archive = set()

    for i in range(len(df)):
        row = df.row(i, named=True)
        if _is_marked_for_archiving(row):
            institutions_to_archive.add(institutions[i].pk)

    return institutions_to_archive


def _is_marked_for_archiving(row: dict[str, Any]) -> bool:
    """Check if a row marks an institution for archiving."""
    archived_value = row.get("archived")
    if archived_value is None:
        return False

    archived_str = str(archived_value).strip().lower()
    return archived_str == "true"


def _apply_archived_status_with_validation(
    institution: Institution,
    row: dict[str, Any],
    institutions_to_archive: set[int],
    parent_children_map: dict[int, list[Institution]],
    result: ImportResult,
) -> bool:
    """
    Apply archived status with validation (without saving).
    Returns True if there was a validation error.
    """
    archived_value = row.get("archived")
    if archived_value is None:
        return False

    archived_str = str(archived_value).strip().lower()

    if archived_str == "true":
        return _validate_and_mark_for_archiving(
            institution, institutions_to_archive, parent_children_map, result
        )

    if archived_str == "false":
        institution.archived_at = None

    return False


def _validate_and_mark_for_archiving(
    institution: Institution,
    institutions_to_archive: set[int],
    parent_children_map: dict[int, list[Institution]],
    result: ImportResult,
) -> bool:
    """Validate that all descendants are archived, then mark institution for archiving."""
    unarchived_children = _get_unarchived_children(
        institution, institutions_to_archive, parent_children_map
    )

    if unarchived_children:
        _add_archive_validation_error(result, institution.name, len(unarchived_children))
        return True

    _mark_institution_for_archiving(institution)
    return False


def _get_unarchived_children(
    institution: Institution,
    institutions_to_archive: set[int],
    parent_children_map: dict[int, list[Institution]],
) -> list[Institution]:
    """Get list of all descendants (at any level) that are not marked for archiving."""
    if not institution.pk:
        return []

    return _get_unarchived_descendants_recursive(
        institution.pk, institutions_to_archive, parent_children_map
    )


def _get_unarchived_descendants_recursive(
    parent_id: int,
    institutions_to_archive: set[int],
    parent_children_map: dict[int, list[Institution]],
) -> list[Institution]:
    """Recursively collect all unarchived descendants at any level."""
    unarchived_descendants: list[Institution] = []

    children = parent_children_map.get(parent_id, [])
    for child in children:
        if child.pk not in institutions_to_archive:
            unarchived_descendants.append(child)

        # Recursively check this child's descendants
        if child.pk:
            unarchived_descendants.extend(
                _get_unarchived_descendants_recursive(
                    child.pk, institutions_to_archive, parent_children_map
                )
            )

    return unarchived_descendants


def _add_archive_validation_error(
    result: ImportResult, institution_name: str, unarchived_count: int
) -> None:
    """Add an error indicating that an institution cannot be archived due to unarchived descendants."""
    descendant_word = "descendant" if unarchived_count == 1 else "descendants"
    result.errors.append(
        ImportError(
            institution_name=institution_name,
            message=f"Cannot archive: has {unarchived_count} unarchived {descendant_word}. All descendants must be marked as archived.",
        )
    )


def _mark_institution_for_archiving(institution: Institution) -> None:
    """Mark an institution for archiving (sets archived_at and virtual fields)."""
    if not institution.archived_at:
        institution.archived_at = timezone.now()
    institution.virtual = True


def _match_by_internal_id_from_lookup(
    row: dict[str, Any], lookups: dict[str, dict[str, Institution]]
) -> Institution | None:
    """Match institution by internal_id using pre-built lookup."""
    internal_id = row.get("internal_id")
    if not internal_id:
        return None

    internal_id_str = str(internal_id).strip()
    if not internal_id_str:
        return None

    institution = lookups["internal_id"].get(internal_id_str)
    if institution:
        institution.name = str(row.get("name"))
        return institution

    return None


def _match_by_external_identifier_from_lookup(
    row: dict[str, Any], lookups: dict[str, dict[str, Institution]]
) -> Institution | None:
    """Match institution by external identifier (ROR, ISNI, Ringgold) using pre-built lookup."""
    for identifier_type in IDENTIFIER_TYPES:
        institution = _try_match_by_identifier(row, lookups, identifier_type)
        if institution:
            institution.name = str(row.get("name"))
            return institution

    return None


def _try_match_by_identifier(
    row: dict[str, Any], lookups: dict[str, dict[str, Institution]], identifier_type: str
) -> Institution | None:
    """Try to match an institution by a specific identifier type."""
    identifier_value = row.get(identifier_type)
    if not identifier_value:
        return None

    identifier_str = str(identifier_value).strip()
    if not identifier_str:
        return None

    lookup_key = identifier_type.lower()
    return lookups[lookup_key].get(identifier_str)


def _get_or_create_by_name_from_lookup(
    row: dict[str, Any], lookups: dict[str, dict[str, Institution]]
) -> Institution:
    """Get existing or create new institution by name using pre-built lookup."""
    name = str(row.get("name", ""))

    # Check if already exists in lookup
    institution = lookups["name"].get(name)
    if institution:
        return institution

    # Create new institution
    new_institution = Institution(name=name)
    lookups["name"][name] = new_institution  # Add to lookup for subsequent rows
    return new_institution


def _set_internal_id_if_needed(institution: Institution, row: dict[str, Any]) -> None:
    """Set internal_id on institution if provided in CSV and not already set."""
    internal_id_value = row.get("internal_id")
    if internal_id_value:
        internal_id_str = str(internal_id_value).strip()
        if internal_id_str and not institution.internal_id:
            institution.internal_id = internal_id_str


def _match_or_create_institutions(df: pl.DataFrame, result: ImportResult) -> list[Institution]:
    # Build lookup tables upfront to avoid N+1 queries
    lookups = _build_matching_lookups(df)

    institutions = []
    for i in range(len(df)):
        row = df.row(i, named=True)

        if institution := _match_by_internal_id_from_lookup(row, lookups):
            result.matched_by_internal_id += 1
        elif institution := _match_by_external_identifier_from_lookup(row, lookups):
            result.matched_by_identifier += 1
        else:
            institution = _get_or_create_by_name_from_lookup(row, lookups)
            result.created_new += 1

        _set_internal_id_if_needed(institution, row)
        institutions.append(institution)

    return institutions


def _build_matching_lookups(df: pl.DataFrame) -> dict[str, dict[str, Institution]]:
    """Build all lookup tables upfront to avoid N+1 queries during matching."""
    lookups: dict[str, dict[str, Institution]] = {
        "internal_id": {},
        "ror": {},
        "isni": {},
        "ringgold": {},
        "name": {},
    }

    # Collect all values from CSV
    csv_values = _collect_values_from_csv(df)

    # Fetch and populate lookups from database
    _populate_internal_id_lookup(lookups, csv_values["internal_ids"])
    _populate_identifier_lookups(lookups, csv_values)
    _populate_name_lookup(lookups, csv_values["names"])

    return lookups


def _collect_values_from_csv(df: pl.DataFrame) -> dict[str, set[str]]:
    """Collect all relevant values from CSV for database lookups."""
    values: dict[str, set[str]] = {
        "internal_ids": set(),
        "ror_values": set(),
        "isni_values": set(),
        "ringgold_values": set(),
        "names": set(),
    }

    for i in range(len(df)):
        row = df.row(i, named=True)

        if internal_id := row.get("internal_id"):
            values["internal_ids"].add(str(internal_id).strip())

        if ror := row.get("ROR"):
            values["ror_values"].add(str(ror).strip())

        if isni := row.get("ISNI"):
            values["isni_values"].add(str(isni).strip())

        if ringgold := row.get("Ringgold"):
            values["ringgold_values"].add(str(ringgold).strip())

        if name := row.get("name"):
            values["names"].add(str(name))

    return values


def _populate_internal_id_lookup(
    lookups: dict[str, dict[str, Institution]], internal_ids: set[str]
) -> None:
    """Fetch and populate the internal_id lookup."""
    if not internal_ids:
        return

    institutions = Institution.all_objects.filter(internal_id__in=internal_ids)
    for inst in institutions:
        if inst.internal_id:
            lookups["internal_id"][inst.internal_id] = inst


def _populate_identifier_lookups(
    lookups: dict[str, dict[str, Institution]], csv_values: dict[str, set[str]]
) -> None:
    """Fetch and populate all identifier lookups (ROR, ISNI, Ringgold)."""
    identifier_config = {
        "ROR": csv_values["ror_values"],
        "ISNI": csv_values["isni_values"],
        "Ringgold": csv_values["ringgold_values"],
    }

    for identifier_type, values in identifier_config.items():
        if values:
            _fetch_and_populate_identifier_lookup(lookups, identifier_type, values)


def _populate_name_lookup(lookups: dict[str, dict[str, Institution]], names: set[str]) -> None:
    """Fetch and populate the name lookup."""
    if not names:
        return

    institutions = Institution.all_objects.filter(name__in=names)
    for inst in institutions:
        lookups["name"][inst.name] = inst


def _fetch_and_populate_identifier_lookup(
    lookups: dict[str, dict[str, Institution]],
    identifier_type: str,
    values: set[str],
) -> None:
    """Fetch institutions by identifier type and populate the lookup."""
    links = InstitutionLink.objects.filter(
        type__name=identifier_type, value__in=values
    ).prefetch_related("institution")

    lookup_key = identifier_type.lower()

    for link in links:
        if link.type.name == identifier_type:
            lookups[lookup_key][link.value] = link.institution


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

    if institution.is_archived():
        raise ValueError("Institution is already archived")

    if replacement is not None:
        institution.archive_with_replacement(replacement, timezone.now())
        _update_home_institution_if_needed(institution, replacement)
        return

    timestamp = timezone.now()
    institution.archive(timestamp)


def restore_without_children(
    institution: Institution, new_parent: Institution | None = None
) -> None:
    institution.restore_without_children(new_parent)


def restore_with_children(institution: Institution, new_parent: Institution | None = None) -> None:
    institution.restore_with_children(new_parent)


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
