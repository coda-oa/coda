import csv
from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandParser

from coda.apps.fundingrequests.models import FundingRequest


class Command(BaseCommand):
    """
    Export contract-related publications from 2025.

    Filters:
    - Only articles (not monographs)
    - Only approved funding requests
    - Must have contract relation with a specified contract year (default=2025)
    - run like this: pdm run manage.py export_contract_publications /app/contract_publications_2024.csv --contract-year 2024
    """

    help = "Export contract-related publications from 2025 to a CSV file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "output_file",
            type=str,
            help="Path to the output CSV file (e.g., contract_publications.csv).",
        )
        parser.add_argument(
            "--contract-year",
            type=int,
            default=2025,
            help="Contract year to filter (default: 2025)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output_file = options["output_file"]
        contract_year = options["contract_year"]
        self.stdout.write(
            f"Exporting contract publications for contract year {contract_year} to {output_file}..."
        )

        # Get approved funding requests with contract-related publications
        approved_funding_requests = (
            FundingRequest.objects.filter(
                review__review_result="approved",
                publication__article_journal__isnull=False,  # Only articles
                publication__attached_contracts__contract_year=contract_year,  # Contract year argument
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
            .distinct()
        )

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
            for fr in approved_funding_requests:
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

                # Get contract info (only selected year contracts)
                contracts_selected = pub.attached_contracts.filter(contract_year=contract_year)

                # Get invoice date (if exists)
                invoice_date = ""
                positions = pub.position_set.select_related("invoice").all()
                if positions:
                    # Get the earliest invoice date
                    for pos in positions:
                        if pos.invoice:
                            invoice_date = str(pos.invoice.date)
                            break

                # Write one row per contract
                for ac in contracts_selected:
                    writer.writerow(
                        [
                            doi,
                            authors,
                            pub.online_publication_date or "",
                            pub.title,
                            invoice_date,
                            ac.contract.name,
                            ac.contract_year,
                            pub_type,
                            pub.open_access_type,
                        ]
                    )
                    count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully exported {count} contract publication records to {output_file}"
            )
        )
