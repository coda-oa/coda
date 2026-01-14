from pathlib import Path
from typing import Any
from django.core.management import BaseCommand, CommandParser

from coda.contexts.fundingrequest.services import import_service


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
            report = import_service.import_fundingrequests(f)

        if report.valid_requests > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{report.valid_requests} funding requests were imported successfully"
                )
            )

        if report.invalid_requests > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"{report.invalid_requests} funding requests could not be imported due to errors"
                )
            )
            errors = "/n".join(f"{request}: {errors}" for request, errors in report.errors.items())
            self.stdout.write(self.style.ERROR(errors))
