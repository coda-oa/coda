from typing import Any

import polars as pl
from django.core.management.base import BaseCommand
from django.db import transaction

from coda.apps.institutions.models import Institution

INSTITUTIONS_LINK = (
    "https://raw.githubusercontent.com/coda-oa/coda-test-data/main/institutions/tubs.csv"
)


class Command(BaseCommand):
    help = "Adds test institutions from TU Braunschweig to the database"

    #: Re-seeding must be idempotent: match existing rows by (name, parent)
    #: and update instead of delete-and-recreate. Institutions are referenced
    #: by Author.affiliation with on_delete=SET_NULL - wiping the table would
    #: silently null every affiliation in the database (and re-seeding with
    #: fresh PKs could not restore them).
    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        df = pl.read_csv(INSTITUTIONS_LINK, separator=";")
        df = df.with_columns(pl.col("Alias").str.strip_chars())

        alias_to_institution = {}

        root_row = df.row(0, named=True)
        root, _ = Institution.objects.update_or_create(
            name=root_row["Name"], defaults={"parent": None}
        )
        root_alias = root_row["Alias"]

        alias_to_institution[root_alias] = root
        alias_to_institution.update(self.add_faculties(df, root, root_alias))
        self.add_institutes(df, alias_to_institution)

    def add_faculties(
        self, df: pl.DataFrame, root: Institution, root_alias: str
    ) -> dict[str, Institution]:
        faculty_rows = df.filter(pl.col("Parent") == root_alias)
        return {
            row["Alias"]: Institution.objects.update_or_create(
                name=row["Name"], parent=root
            )[0]
            for row in faculty_rows.rows(named=True)
        }

    def add_institutes(
        self, df: pl.DataFrame, alias_to_institution: dict[str, Institution]
    ) -> None:
        institute_rows = df.filter(
            pl.col("Parent").is_in(alias_to_institution.keys()) & pl.col("Alias").is_null()
        )
        for row in institute_rows.rows(named=True):
            Institution.objects.update_or_create(
                name=row["Name"], parent=alias_to_institution[row["Parent"]]
            )
