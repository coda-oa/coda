from typing import ClassVar

from django.db import models


class FundingRequestCSVExport(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    filters = models.JSONField(help_text="Filter criteria used to generate this export")
    record_count = models.IntegerField(help_text="Number of rows in export at creation time")
    csv_content = models.TextField(
        blank=True,
        default="",
        help_text="Generated CSV snapshot; empty string means the artifact is unavailable",
    )

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "Funding Request CSV Export"
        verbose_name_plural = "Funding Request CSV Exports"

    def __str__(self) -> str:
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d')})"
