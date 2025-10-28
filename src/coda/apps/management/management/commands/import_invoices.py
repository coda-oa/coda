from pathlib import Path
from typing import Any

from django.core.management import BaseCommand, CommandParser

from coda.contexts.finance.services import import_service


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
            result = import_service.import_invoices(f)
            for number, errors in result.errors.items():
                self.stdout.write(self.style.ERROR(f"Error importing invoice: {number}"))
                self.stdout.write(self.style.ERROR(f"Errors: {', '.join(errors)}"))

        self.stdout.write(self.style.SUCCESS("Invoices imported successfully."))
