import datetime
import enum
import uuid
from typing import Any

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse

from coda.apps.authors.models import Author
from coda.apps.publications.models import Publication


class FundingOrganization(models.Model):
    name = models.CharField()

    def __str__(self) -> str:
        return self.name


class ExternalFunding(models.Model):
    organization = models.ForeignKey(FundingOrganization, on_delete=models.CASCADE)
    project_id = models.CharField()
    project_name = models.CharField()


class Label(models.Model):
    name = models.CharField(max_length=50)
    color_validator = RegexValidator(
        regex=r"^#[a-fA-F0-9]{6}$", message="Color must be in the format #RRGGBB"
    )
    hexcolor = models.CharField(max_length=7, validators=[color_validator])

    def __str__(self) -> str:
        return self.name


class ProcessingStatus(enum.Enum):
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    REJECTED = "rejected"

    def __str__(self) -> str:
        return self.value


class PaymentMethod(enum.Enum):
    DIRECT = "direct"
    REIMBURSEMENT = "reimbursement"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


class FundingRequest(models.Model):
    @staticmethod
    def create_request_id(id: str | None = None, date: datetime.date | None = None) -> str:
        id = id or uuid.uuid4().hex[:8]
        d = date or datetime.date.today()
        return f"coda-{id}-{d.strftime('%Y-%m-%d')}"

    PROCESSING_CHOICES = [
        (ProcessingStatus.APPROVED.value, "Approved"),
        (ProcessingStatus.IN_PROGRESS.value, "In Progress"),
        (ProcessingStatus.REJECTED.value, "Rejected"),
    ]

    PAYMENT_METHOD_CHOICES = [
        (PaymentMethod.DIRECT.value, "Direct"),
        (PaymentMethod.REIMBURSEMENT.value, "Reimbursement"),
        (PaymentMethod.UNKNOWN.value, "Unknown"),
    ]

    request_id = models.CharField(max_length=25, unique=True)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_cost_currency = models.CharField(max_length=3)
    payment_method = models.CharField(
        choices=PAYMENT_METHOD_CHOICES, default=PaymentMethod.UNKNOWN.value
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_CHOICES, default="in_progress"
    )
    labels = models.ManyToManyField(Label, related_name="requests")
    submitter = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="funding_requests", null=True, blank=True
    )
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    external_funding = models.ForeignKey(
        ExternalFunding, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.request_id:
            self.request_id = self.create_request_id()

    def get_absolute_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.pk})

    def approve(self) -> None:
        self.processing_status = ProcessingStatus.APPROVED.value
        self.save()

    def reject(self) -> None:
        self.processing_status = ProcessingStatus.REJECTED.value
        self.save()

    def open(self) -> None:
        self.processing_status = ProcessingStatus.IN_PROGRESS.value
        self.save()

    def is_approved(self) -> bool:
        return self.processing_status == ProcessingStatus.APPROVED.value

    def is_rejected(self) -> bool:
        return self.processing_status == ProcessingStatus.REJECTED.value

    def is_open(self) -> bool:
        return self.processing_status == ProcessingStatus.IN_PROGRESS.value
