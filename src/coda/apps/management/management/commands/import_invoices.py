from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandParser

from coda.contexts.finance.services.invoice_import import import_invoices


class Command(BaseCommand):
    """
    Command to import funding requests from a JSON file.
    """

    help = "Import funding requests from a JSON file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to the JSON file containing funding requests.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        file = options["json_file"]
        self.stdout.write(f"Importing invoices from {file}...")
        with Path(file).open("r") as f:
            result = import_invoices(f)
            for error in result.errors:
                self.stdout.write(
                    self.style.ERROR(f"Error importing invoice: {error.invoice_number}")
                )
                self.stdout.write(self.style.ERROR(f"Errors: {', '.join(error.reasons)}"))

        self.stdout.write(self.style.SUCCESS("Invoices imported successfully."))
