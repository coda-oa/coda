from typing import Any

import polars as pl
from django.core.management.base import BaseCommand
from django.db import transaction

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class Command(BaseCommand):
    help = "Add journals for testing purposes from GitHub"

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        self.delete_old_data()
        df = self.download_test_data()
        self.add_publishers(df)
        self.add_journals(df)

    def delete_old_data(self) -> None:
        self.stdout.write("Delete all journals")
        journals = Journal.objects.all()
        journals.delete()

        self.stdout.write("Delete all publishers")
        publishers = Publisher.objects.all()
        publishers.delete()

    def download_test_data(self) -> pl.DataFrame:
        self.stdout.write("Downloading journals from GitHub")
        df = pl.read_csv(
            "https://raw.githubusercontent.com/coda-oa/coda-test-data/main/journals.csv"
        )

        return df

    def add_publishers(self, df: pl.DataFrame) -> None:
        self.stdout.write("Adding publishers")
        publishers = df["publisher"].unique().to_list()
        Publisher.objects.bulk_create([Publisher(name=publisher) for publisher in publishers])

    def add_journals(self, df: pl.DataFrame) -> None:
        self.stdout.write("Add journals from GitHub")
        Journal.objects.bulk_create(
            [
                Journal(
                    title=row["journal_title"],
                    publisher=Publisher.objects.get(name=row["publisher"]),
                    eissn=row["e_issn"].strip(),
                    open_access_type=row["journal_type"],
                    licenses=row["license"],
                    successor_to=None,
                )
                for row in df.rows(named=True)
            ]
        )
