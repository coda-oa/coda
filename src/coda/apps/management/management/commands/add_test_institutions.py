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

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        Institution.objects.all().delete()

        df = pl.read_csv(INSTITUTIONS_LINK, separator=";")
        df = df.with_columns(pl.col("Alias").str.strip_chars())

        alias_to_institution = {}

        root_row = df.row(0, named=True)
        root = Institution.objects.create(name=root_row["Name"])
        root_alias = root_row["Alias"]

        alias_to_institution[root_alias] = root
        alias_to_institution.update(self.add_faculties(df, root, root_alias))
        self.add_institutes(df, alias_to_institution)

    def add_faculties(
        self, df: pl.DataFrame, root: Institution, root_alias: str
    ) -> dict[str, Institution]:
        faculty_rows = df.filter(pl.col("Parent") == root_alias)
        Institution.objects.bulk_create(
            Institution(name=row["Name"], parent=root) for row in faculty_rows.rows(named=True)
        )

        return {
            row["Alias"]: Institution.objects.get(name=row["Name"])
            for row in faculty_rows.rows(named=True)
        }

    def add_institutes(
        self, df: pl.DataFrame, alias_to_institution: dict[str, Institution]
    ) -> None:
        institute_rows = df.filter(
            pl.col("Parent").is_in(alias_to_institution.keys()) & pl.col("Alias").is_null()
        )
        Institution.objects.bulk_create(
            Institution(
                name=row["Name"],
                parent=alias_to_institution[row["Parent"]],
            )
            for row in institute_rows.rows(named=True)
        )
