from django.db import models
from django.utils import timezone


class OpenCostReport(models.Model):
    title = models.CharField(max_length=255)
    period_start = models.DateField(help_text="Start of reporting period")
    period_end = models.DateField(help_text="End of reporting period")
    filters = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(
        default=timezone.now, help_text="When this report was generated"
    )

    # Generated artifacts (written once per generation)
    xml_content = models.TextField(
        blank=True,
        default="",
        help_text="Generated openCost XML; empty string means nothing was exportable",
    )
    issues = models.JSONField(
        default=list,
        help_text="Validation issues as list of serialized ValidationWarning dicts",
    )

    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "OpenCost Report"
        verbose_name_plural = "OpenCost Reports"

    def __str__(self) -> str:
        return f"{self.title} ({self.period_start} to {self.period_end})"

    def _issue_counts(self) -> dict[str, int]:
        """Validation issue counts derived from the stored ``issues`` JSON.

        The JSON loads with the row, so counting it costs no query; the counts
        are exactly the log's contents, with nothing kept alongside to disagree.
        """
        issues = self.issues or []
        return {
            "errors": sum(1 for w in issues if w.get("level") == "error"),
            "warnings": sum(1 for w in issues if w.get("level") == "warning"),
        }

    def has_issues(self) -> bool:
        """Check if report has any validation issues."""
        counts = self._issue_counts()
        return counts["errors"] > 0 or counts["warnings"] > 0

    def get_issue_counts(self) -> dict[str, int]:
        """Get validation issue counts as ``{"errors": int, "warnings": int}``."""
        return self._issue_counts()


class OpenCostReportPublication(models.Model):
    report = models.ForeignKey(
        OpenCostReport,
        on_delete=models.CASCADE,
        related_name="publications",
        help_text="The report this publication belongs to",
    )

    publication = models.ForeignKey(
        "publications.Publication",
        on_delete=models.CASCADE,
        help_text="Original CODA publication (for navigation links)",
    )

    title = models.CharField(max_length=500, help_text="Publication title (snapshot)")
    publisher = models.CharField(max_length=500, blank=True, help_text="Publisher name (snapshot)")

    exported = models.BooleanField(
        default=False,
        help_text="Whether this publication was included in the generated XML",
    )
    had_errors = models.BooleanField(
        default=False,
        help_text="Whether generation recorded an error-level issue for this publication",
    )
    xml_ordinal = models.IntegerField(
        null=True,
        blank=True,
        help_text="Index of this publication's entry in the generated XML; None when excluded",
    )

    class Meta:
        # Id order: deterministic iteration, independent of snapshot content.
        ordering = ["id"]
        unique_together = ("report", "publication")
        verbose_name = "Report Publication"
        verbose_name_plural = "Report Publications"

    def __str__(self) -> str:
        return f"{self.title} (in {self.report.title})"


class OpenCostReportInvoice(models.Model):
    report_publication = models.ForeignKey(
        OpenCostReportPublication,
        on_delete=models.CASCADE,
        related_name="invoices",
        help_text="The report publication this invoice belongs to",
    )

    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.CASCADE,
        help_text="Original CODA invoice (for navigation links)",
    )

    exported = models.BooleanField(
        default=False,
        help_text="Whether this invoice was included in the generated XML",
    )
    had_errors = models.BooleanField(
        default=False,
        help_text="Whether generation recorded an error-level issue for this invoice",
    )
    xml_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Index of this invoice within its parent's exported invoices in the XML; "
        "None when excluded",
    )

    class Meta:
        # Id order: deterministic iteration, independent of snapshot content.
        ordering = ["id"]
        unique_together = ("report_publication", "invoice")
        verbose_name = "Report Invoice"
        verbose_name_plural = "Report Invoices"

    def __str__(self) -> str:
        return f"Invoice {self.invoice.number} for {self.report_publication.title}"


class OpenCostReportContract(models.Model):
    report = models.ForeignKey(
        OpenCostReport,
        on_delete=models.CASCADE,
        related_name="contracts",
        help_text="The report this contract belongs to",
    )

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        help_text="Original CODA contract (for navigation links)",
    )

    exported = models.BooleanField(
        default=False,
        help_text="Whether this contract was included in the generated XML",
    )
    had_errors = models.BooleanField(
        default=False,
        help_text="Whether generation recorded an error-level issue for this contract",
    )
    xml_ordinal = models.IntegerField(
        null=True,
        blank=True,
        help_text="Index of this contract's entry in the generated XML; None when excluded",
    )

    class Meta:
        # Id order: deterministic iteration, independent of snapshot content.
        ordering = ["id"]
        unique_together = ("report", "contract")
        verbose_name = "Report Contract"
        verbose_name_plural = "Report Contracts"

    def __str__(self) -> str:
        return f"{self.contract.name} (in {self.report.title})"


class OpenCostReportContractInvoice(models.Model):
    report_contract = models.ForeignKey(
        OpenCostReportContract,
        on_delete=models.CASCADE,
        related_name="invoices",
        help_text="The report contract this invoice belongs to",
    )

    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.CASCADE,
        help_text="Original CODA invoice (for navigation links)",
    )

    exported = models.BooleanField(
        default=False,
        help_text="Whether this invoice was included in the generated XML",
    )
    had_errors = models.BooleanField(
        default=False,
        help_text="Whether generation recorded an error-level issue for this invoice",
    )
    xml_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Index of this invoice within its parent's exported invoices in the XML; "
        "None when excluded",
    )

    class Meta:
        # Id order: deterministic iteration, independent of snapshot content.
        ordering = ["id"]
        unique_together = ("report_contract", "invoice")
        verbose_name = "Report Contract Invoice"
        verbose_name_plural = "Report Contract Invoices"

    def __str__(self) -> str:
        return f"Invoice {self.invoice.number} for {self.report_contract.contract.name}"
