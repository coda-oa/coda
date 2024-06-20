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
        self.delete_old_data()
        df = self.download_test_data()
        self.add_publishers(df)
        self.add_journals(df)
        self.add_contracts(df)

    def delete_old_data(self) -> None:
        self.stdout.write("Delete all journals")
        journals = Journal.objects.all()
        journals.delete()

        self.stdout.write("Delete all publishers")
        publishers = Publisher.objects.all()
        publishers.delete()

        self.stdout.write("Delete all contracts")
        contracts = Contract.objects.all()
        contracts.delete()

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
        df = df.drop_nulls("e_issn")
        Journal.objects.bulk_create(
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

    def add_contracts(self, df: pl.DataFrame) -> None:
        self.stdout.write("Adding Contracts")
        journals_with_contract = df.filter(pl.col("contract").is_not_null()).sort("e_issn")
        e_issns = set(journals_with_contract["e_issn"].unique().to_list())
        journals = Journal.objects.filter(eissn__in=e_issns).order_by("eissn")
        for row, journal in zip(journals_with_contract.rows(named=True), journals):
            assert journal.eissn == row["e_issn"]
            contract_name = row["contract"]
            contract, created = Contract.objects.get_or_create(name=contract_name)
            if created:
                contract.start_date = datetime.date(2024, 1, 1)
                contract.end_date = datetime.date(2028, 12, 31)

            contract.publishers.add(journal.publisher)
            journal.contracts.add(contract)
            journal.save()
            contract.save()
