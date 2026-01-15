from io import BytesIO, StringIO
from typing import Any

import polars as pl

from coda.apps.institutions.models import Institution, InstitutionLinkType
from coda.domain.institution.links import create_link

from dataclasses import dataclass, field


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
