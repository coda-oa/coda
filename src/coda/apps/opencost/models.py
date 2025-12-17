from functools import cached_property

from django.db import models
from django.utils import timezone

from coda.apps.opencost.validation import validate_report, ValidationWarning


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

    @cached_property
    def validation_warnings(self) -> list[ValidationWarning]:
        """Cache validation results to avoid repeated calls."""
        return validate_report(self)

    def has_issues(self) -> bool:
        return len(self.validation_warnings) > 0

    def get_issue_counts(self) -> dict[str, int]:
        return {
            "errors": sum(1 for w in self.validation_warnings if w.level == "error"),
            "warnings": sum(1 for w in self.validation_warnings if w.level == "warning"),
        }


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

    institution_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Institution name (snapshot)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["title"]
        unique_together = ("report", "publication")
        verbose_name = "Report Publication"
        verbose_name_plural = "Report Publications"

    def __str__(self) -> str:
        return f"{self.title} (in {self.report.title})"


class OpenCostReportInstitutionIdentifier(models.Model):
    report_publication = models.ForeignKey(
        OpenCostReportPublication,
        on_delete=models.CASCADE,
        related_name="institution_identifiers",
        help_text="The report publication this institution identifier belongs to",
    )

    identifier_type = models.CharField(
        max_length=50,
        help_text="Type of identifier: ror, isni, or ringold (snapshot)",
    )
    value = models.CharField(
        max_length=500,
        help_text="Institution identifier value (snapshot)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["identifier_type", "value"]
        verbose_name = "Report Institution Identifier"
        verbose_name_plural = "Report Institution Identifiers"

    def __str__(self) -> str:
        return f"{self.identifier_type}: {self.value}"


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

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["link_type", "value"]
        verbose_name = "Report Publication Link"
        verbose_name_plural = "Report Publication Links"

    def __str__(self) -> str:
        return f"{self.link_type}: {self.value}"


class OpenCostReportPublicationContract(models.Model):
    """Snapshot of publication-contract relationship for part_of_contract in OpenCost."""

    report_publication = models.ForeignKey(
        OpenCostReportPublication,
        on_delete=models.CASCADE,
        related_name="linked_contracts",
        help_text="The report publication this contract link belongs to",
    )

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        help_text="Contract this publication is part of",
    )

    contract_year = models.IntegerField(
        help_text="Year of contract participation (snapshot from AttachedContract)"
    )

    group_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional group ID for OpenCost part_of_contract",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["contract_year"]
        unique_together = ("report_publication", "contract")
        verbose_name = "Report Publication Contract"
        verbose_name_plural = "Report Publication Contracts"

    def __str__(self) -> str:
        return f"{self.report_publication.title} -> {self.contract.name} ({self.contract_year})"


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

    snapshot_date = models.DateTimeField(default=timezone.now)

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

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["amount"]
        verbose_name = "Report Invoice Position"
        verbose_name_plural = "Report Invoice Positions"

    def __str__(self) -> str:
        return f"{self.amount} {self.currency} ({self.cost_type})"


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

    contract_name = models.CharField(max_length=255, help_text="Contract name (snapshot)")

    institution_name = models.CharField(
        max_length=500,
        blank=True,
        help_text="Institution name (snapshot)",
    )

    participation_from = models.DateField(
        null=True, blank=True, help_text="Contract participation start date (snapshot)"
    )
    participation_to = models.DateField(
        null=True, blank=True, help_text="Contract participation end date (snapshot)"
    )

    primary_identifier_value = models.CharField(
        max_length=500, blank=True, help_text="Primary identifier value (ESAC ID) (snapshot)"
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["contract_name"]
        unique_together = ("report", "contract")
        verbose_name = "Report Contract"
        verbose_name_plural = "Report Contracts"

    def __str__(self) -> str:
        return f"{self.contract_name} (in {self.report.title})"


class OpenCostReportContractInstitutionIdentifier(models.Model):
    report_contract = models.ForeignKey(
        OpenCostReportContract,
        on_delete=models.CASCADE,
        related_name="institution_identifiers",
        help_text="The report contract this institution identifier belongs to",
    )

    identifier_type = models.CharField(
        max_length=50,
        help_text="Type of identifier: ror, isni, or ringold (snapshot)",
    )
    value = models.CharField(
        max_length=500,
        help_text="Institution identifier value (snapshot)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["identifier_type", "value"]
        verbose_name = "Report Contract Institution Identifier"
        verbose_name_plural = "Report Contract Institution Identifiers"

    def __str__(self) -> str:
        return f"{self.identifier_type}: {self.value}"


class OpenCostReportContractSecondaryIdentifier(models.Model):
    report_contract = models.ForeignKey(
        OpenCostReportContract,
        on_delete=models.CASCADE,
        related_name="secondary_identifiers",
        help_text="The report contract this secondary identifier belongs to",
    )

    identifier_type = models.CharField(
        max_length=50,
        help_text="Type of identifier: oai, ezb, or local (snapshot)",
    )
    value = models.CharField(
        max_length=500,
        help_text="Secondary identifier value (snapshot)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["identifier_type", "value"]
        verbose_name = "Report Contract Secondary Identifier"
        verbose_name_plural = "Report Contract Secondary Identifiers"

    def __str__(self) -> str:
        return f"{self.identifier_type}: {self.value}"


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

    invoice_number = models.CharField(
        max_length=255, blank=True, help_text="Invoice number (snapshot)"
    )
    creditor = models.CharField(
        max_length=255, blank=True, help_text="Creditor/publisher name (snapshot)"
    )
    invoice_date = models.DateField(null=True, blank=True, help_text="Invoice date (snapshot)")

    amount_invoice = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Total invoice amount (snapshot)",
    )
    amount_invoice_currency = models.CharField(
        max_length=3, blank=True, help_text="Invoice amount currency (snapshot)"
    )

    group_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="UUID4 to group invoices and link to publications (for part_of_contract)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["invoice_number"]
        unique_together = ("report_contract", "invoice")
        verbose_name = "Report Contract Invoice"
        verbose_name_plural = "Report Contract Invoices"

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number} for {self.report_contract.contract_name}"


class OpenCostReportContractInvoicePosition(models.Model):
    report_contract_invoice = models.ForeignKey(
        OpenCostReportContractInvoice,
        on_delete=models.CASCADE,
        related_name="positions",
        help_text="The report contract invoice this position belongs to",
    )

    position = models.ForeignKey(
        "invoices.Position", on_delete=models.CASCADE, help_text="Original CODA position"
    )

    amount = models.DecimalField(
        max_digits=20, decimal_places=4, help_text="Cost amount (snapshot)"
    )
    currency = models.CharField(max_length=3, help_text="Currency code (snapshot)")
    cost_type = models.CharField(
        max_length=50, help_text="OpenCost contract cost type (publish/read/vat) (snapshot)"
    )
    vat = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="VAT/tax amount (snapshot)",
    )

    snapshot_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["amount"]
        verbose_name = "Report Contract Invoice Position"
        verbose_name_plural = "Report Contract Invoice Positions"

    def __str__(self) -> str:
        return f"{self.amount} {self.currency} ({self.cost_type})"
