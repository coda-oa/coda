from pathlib import Path
from typing import Any
from django.core.management import BaseCommand, CommandParser

from coda.apps.fundingrequests.services import importservice


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
        self.stdout.write(f"Importing funding requests from {file}...")
        with Path(file).open("r") as f:
            importservice.import_fundingrequests(f)

        self.stdout.write(self.style.SUCCESS("Funding requests imported successfully."))
