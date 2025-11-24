from django.db import models
from django.utils import timezone


class OpenCostReport(models.Model):
    title = models.CharField(max_length=255)
    period_start = models.DateField(help_text="Start of reporting period")
    period_end = models.DateField(help_text="End of reporting period")
    generated_at = models.DateTimeField(
        default=timezone.now, help_text="When this report was generated"
    )

    xml_content = models.TextField(blank=True, help_text="Generated OpenCost XML")

    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "OpenCost Report"
        verbose_name_plural = "OpenCost Reports"

    def __str__(self) -> str:
        return f"{self.title} ({self.period_start} to {self.period_end})"


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
    doi = models.CharField(max_length=255, blank=True, help_text="DOI (snapshot)")
    publication_type = models.CharField(
        max_length=100, help_text="COAR publication type (snapshot)"
    )
    publisher = models.CharField(max_length=500, blank=True, help_text="Publisher name (snapshot)")
    journal = models.CharField(max_length=500, blank=True, help_text="Journal name (snapshot)")

    external_costsplitting = models.BooleanField(
        null=True, blank=True, help_text="Whether publication has multi-institutional cost sharing"
    )

    snapshot_date = models.DateTimeField(
        default=timezone.now, help_text="When this snapshot was created"
    )

    class Meta:
        ordering = ["title"]
        unique_together = ("report", "publication")
        verbose_name = "Report Publication"
        verbose_name_plural = "Report Publications"

    def __str__(self) -> str:
        return f"{self.title} (in {self.report.title})"


class OpenCostReportPublicationLink(models.Model):
    report_publication = models.ForeignKey(
        OpenCostReportPublication,
        on_delete=models.CASCADE,
        related_name="links",
        help_text="The report publication this link belongs to",
    )

    link_type = models.CharField(
        max_length=50, help_text="Link type (e.g., 'handle', 'urn') (snapshot)"
    )
    value = models.CharField(max_length=500, help_text="Link value/identifier (snapshot)")

    snapshot_date = models.DateTimeField(
        default=timezone.now, help_text="When this snapshot was created"
    )

    class Meta:
        ordering = ["link_type", "value"]
        verbose_name = "Report Publication Link"
        verbose_name_plural = "Report Publication Links"

    def __str__(self) -> str:
        return f"{self.link_type}: {self.value}"


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

    invoice_number = models.CharField(
        max_length=255, blank=True, help_text="Invoice number (snapshot)"
    )
    creditor = models.CharField(
        max_length=255, blank=True, help_text="Creditor/publisher name (snapshot)"
    )
    invoice_date = models.DateField(null=True, blank=True, help_text="Invoice date (snapshot)")

    snapshot_date = models.DateTimeField(
        default=timezone.now, help_text="When this snapshot was created"
    )

    class Meta:
        ordering = ["invoice_number"]
        unique_together = ("report_publication", "invoice")
        verbose_name = "Report Invoice"
        verbose_name_plural = "Report Invoices"

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number} for {self.report_publication.title}"


class OpenCostReportInvoicePosition(models.Model):
    report_invoice = models.ForeignKey(
        OpenCostReportInvoice,
        on_delete=models.CASCADE,
        related_name="positions",
        help_text="The report invoice this position belongs to",
    )

    position = models.ForeignKey(
        "invoices.Position", on_delete=models.CASCADE, help_text="Original CODA position"
    )

    amount = models.DecimalField(
        max_digits=20, decimal_places=4, help_text="Cost amount (snapshot)"
    )
    currency = models.CharField(max_length=3, help_text="Currency code (snapshot)")
    cost_type = models.CharField(max_length=50, help_text="OpenCost cost type (snapshot)")
    vat = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="VAT/tax amount (snapshot)",
    )

    snapshot_date = models.DateTimeField(
        default=timezone.now, help_text="When this snapshot was created"
    )

    class Meta:
        ordering = ["amount"]
        verbose_name = "Report Invoice Position"
        verbose_name_plural = "Report Invoice Positions"

    def __str__(self) -> str:
        return f"{self.amount} {self.currency} ({self.cost_type})"
