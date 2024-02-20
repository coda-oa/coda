import datetime
import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from coda.apps.authors.models import Author

from coda.apps.publications.models import Publication


class Label(models.Model):
    name = models.CharField(max_length=50)
    color_validator = RegexValidator(
        regex=r"^#[a-fA-F0-9]{6}$", message="Color must be in the format #RRGGBB"
    )
    hexcolor = models.CharField(max_length=7, validators=[color_validator])


class FundingRequest(models.Model):
    @staticmethod
    def create_request_id(id: str | None = None, date: datetime.date | None = None) -> str:
        id = id or uuid.uuid4().hex[:6]
        d = date or datetime.date.today()
        return f"coda-{id}-{d.strftime('%Y-%m-%d')}"

    PROCESSING_CHOICES = [
        ("approved", "Approved"),
        ("in_progress", "In Progress"),
        ("rejected", "Rejected"),
    ]

    request_id = models.CharField(max_length=23, unique=True, default=create_request_id())
    submitter = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="funding_requests", null=True, blank=True
    )
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_cost_currency = models.CharField(max_length=3)
    processing_status = models.CharField(max_length=20, choices=PROCESSING_CHOICES)
    labels = models.ManyToManyField(Label, related_name="requests")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.pk})
