import csv
from datetime import date
from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandParser

from coda.apps.fundingrequests.models import FundingRequest


class Command(BaseCommand):
    """
    Export standalone (non-contract) Gold OA publications from 2025.

    Filters:
    - Only articles (not monographs)
    - Only approved funding requests
    - Online publication date within 2025
    - No contract relation
    - Open Access Type = Gold

    - run like this: pdm run manage.py export_standalone_publications /app/standalone_publications_2024.csv --year 2024
    """

    help = "Export standalone Gold OA publications from 2025 to a CSV file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "output_file",
            type=str,
            help="Path to the output CSV file (e.g., standalone_publications_2025.csv).",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="Online publication year to export (default: 2025)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output_file = options["output_file"]
        year = options["year"]
        self.stdout.write(f"Exporting standalone publications for year {year} to {output_file}...")

        # Get approved funding requests with standalone Gold OA publications from the specified year
        approved_funding_requests = (
            FundingRequest.objects.filter(
                review__review_result="approved",
                publication__article_journal__isnull=False,  # Only articles
                publication__online_publication_date__gte=date(year, 1, 1),
                publication__online_publication_date__lt=date(year + 1, 1, 1),
                publication__open_access_type="Gold",  # Only Gold OA
            )
            .select_related(
                "publication",
                "publication__article_journal",
                "publication__publication_type",
            )
            .prefetch_related(
                "publication__links",
                "publication__links__type",
                "publication__attached_contracts__contract",
                "publication__relevant_authors",
            )
        )

        # Filter out publications that have contracts
        funding_requests_without_contracts = []
        for fr in approved_funding_requests:
            if not fr.publication.attached_contracts.exists():
                funding_requests_without_contracts.append(fr)

        # Write to CSV
        with Path(output_file).open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            writer.writerow(
                [
                    "DOI",
                    "Authors",
                    "Online Publication Date",
                    "Title",
                    "Invoice Date",
                    "Contract",
                    "Contract Year",
                    "Publication Type",
                    "Open Access Type",
                ]
            )

            # Write data
            count = 0
            for fr in funding_requests_without_contracts:
                pub = fr.publication
                # Get DOI
                doi = ""
                for link in pub.links.all():
                    if link.type and link.type.name.upper() == "DOI":
                        doi = link.value
                        break

                # Get all authors (relevant_authors + author_list)
                authors_list = []
                for author in pub.relevant_authors.all():
                    authors_list.append(author.name)
                if pub.author_list:
                    authors_list.append(pub.author_list)
                authors = ", ".join(authors_list)

                # Get publication type
                pub_type = pub.publication_type.name if pub.publication_type else ""

                # Get invoice date (if exists)
                invoice_date = ""
                positions = pub.position_set.select_related("invoice").all()
                if positions:
                    # Get the earliest invoice date
                    for pos in positions:
                        if pos.invoice:
                            invoice_date = str(pos.invoice.date)
                            break

                writer.writerow(
                    [
                        doi,
                        authors,
                        pub.online_publication_date or "",
                        pub.title,
                        invoice_date,
                        "",  # No contract
                        "",  # No contract year
                        pub_type,
                        pub.open_access_type,
                    ]
                )
                count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully exported {count} standalone publication records to {output_file}"
            )
        )
