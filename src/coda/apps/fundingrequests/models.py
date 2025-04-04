from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse

from coda.apps.publications.models import Publication
from coda.domain.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult


class FundingRequestContact(models.Model):
    name = models.CharField()
    email = models.EmailField()

    def __str__(self) -> str:
        return self.name


class FundingOrganization(models.Model):
    name = models.CharField()

    def __str__(self) -> str:
        return self.name


class ExternalFunding(models.Model):
    funding_request = models.ForeignKey(
        "FundingRequest",
        on_delete=models.CASCADE,
        related_name="external_funding",
        null=True,
    )
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


class FundingRequestReview(models.Model):
    review_result = models.CharField(max_length=20, default="open")
    decided_funding_amount = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    decided_funding_currency = models.CharField(max_length=3, blank=True)
    remarks = models.TextField(blank=True)


class FundingRequest(models.Model):
    PROCESSING_CHOICES = [
        (ReviewResult.Approved.value, "Approved"),
        (ReviewResult.Open.value, "In Progress"),
        (ReviewResult.Rejected.value, "Rejected"),
    ]

    PAYMENT_METHOD_CHOICES = [
        (PaymentMethod.Direct.value, "Direct"),
        (PaymentMethod.Reimbursement.value, "Reimbursement"),
        (PaymentMethod.Unknown.value, "Unknown"),
    ]

    request_id = models.CharField(max_length=26, unique=True)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=4)
    estimated_cost_currency = models.CharField(max_length=3)
    payment_method = models.CharField(
        choices=PAYMENT_METHOD_CHOICES, default=PaymentMethod.Unknown.value
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    labels = models.ManyToManyField(Label, related_name="requests")
    extra_contact = models.OneToOneField(
        FundingRequestContact, related_name="funding_request", on_delete=models.SET_NULL, null=True
    )
    publication = models.OneToOneField(Publication, on_delete=models.CASCADE)

    request_remarks = models.TextField(blank=True)

    review = models.OneToOneField(
        "FundingRequestReview", on_delete=models.CASCADE, related_name="fundingrequest"
    )

    def get_absolute_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.pk})
