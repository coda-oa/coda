import datetime
from typing import Any

import polars as pl
from django.core.management.base import BaseCommand
from django.db import transaction

from coda.apps.contracts.models import Contract
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


class Command(BaseCommand):
    help = "Add journals for testing purposes from GitHub"

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        df = self.download_test_data()
        self.stdout.write("Parsing publishers")
        publishers = self.add_publishers(df)
        self.stdout.write(f"Added {self.num_created(publishers)} publishers")

        self.stdout.write("Parsing journals")
        journals = self.add_journals(df)
        self.stdout.write(f"Added {len(journals)} journals")

        self.stdout.write("Parsing contracts")
        contracts = self.add_contracts(df)
        self.stdout.write(f"Added {len(contracts)} contracts")

    def download_test_data(self) -> pl.DataFrame:
        self.stdout.write("Downloading journals from GitHub")
        return pl.read_csv(
            "https://raw.githubusercontent.com/coda-oa/coda-test-data/main/journals.csv"
        )

    def add_publishers(self, df: pl.DataFrame) -> list[tuple[Publisher, bool]]:
        publishers = df["publisher"].unique().to_list()
        return [Publisher.objects.get_or_create(name=publisher) for publisher in publishers]

    def num_created(self, publisher_objects: list[tuple[Publisher, bool]]) -> int:
        return sum([int(created) for _, created in publisher_objects])

    def add_journals(self, df: pl.DataFrame) -> list[Journal]:
        df = self.clean_eissn(df)
        existing = self.find_existing(df)
        df = self.exclude_existing_issns(df, existing)

        journals = Journal.objects.bulk_create(
            [
                Journal(
                    title=row["journal_title"],
                    publisher=Publisher.objects.get(name=row["publisher"]),
                    eissn=row["e_issn"].strip(),
                    licenses=row["license"],
                    predecessor=None,
                )
                for row in df.rows(named=True)
            ]
        )

        return journals

    def clean_eissn(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.drop_nulls("e_issn").with_columns(pl.col("e_issn").str.strip_chars())

    def find_existing(self, df: pl.DataFrame) -> set[str]:
        eissn_series = df["e_issn"].unique()
        e_issns = set(eissn_series.to_list())
        existing = Journal.objects.filter(eissn__in=e_issns).values_list("eissn", flat=True)
        self.stdout.write(
            f"{len(existing)} journals from the DataFrame already exist in the database"
        )
        return set(existing)

    def exclude_existing_issns(self, df: pl.DataFrame, existing: set[str]) -> pl.DataFrame:
        return df.filter(pl.col("e_issn").is_in(existing).not_())

    def add_contracts(self, df: pl.DataFrame) -> list[Contract]:
        journals_with_contract = df.filter(pl.col("contract").is_not_null()).sort("e_issn")
        e_issns = set(journals_with_contract["e_issn"].unique().to_list())
        journals = Journal.objects.filter(eissn__in=e_issns).order_by("eissn")

        created_contracts: list[Contract] = []
        for row, journal in zip(journals_with_contract.rows(named=True), journals):
            assert journal.eissn == row["e_issn"]
            contract_name = row["contract"]
            contract, created = Contract.objects.get_or_create(name=contract_name)
            if created:
                created_contracts.append(contract)
                self.stdout.write(f"Created contract {contract_name}")
                contract.start_date = datetime.date(2024, 1, 1)
                contract.end_date = datetime.date(2028, 12, 31)

            contract.publishers.add(journal.publisher)
            journal.contracts.add(contract)
            journal.save()
            contract.save()

        return created_contracts
