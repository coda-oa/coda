from typing import Any
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


class FundingRequestQuerySet(models.QuerySet["FundingRequest"]):
    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        publication_ids = self.values_list("publication_id", flat=True)
        publication_qs = Publication.objects.filter(id__in=publication_ids)
        publication_deletions = [publication_qs.delete()[1]] if publication_ids else []

        deleted_entity_names = {
            key for deletion in publication_deletions for key in deletion.keys()
        }
        counted_deletions = {entity_name: 0 for entity_name in deleted_entity_names}
        counted_deletions.update(
            {
                entity_name: sum(deletion.get(entity_name, 0) for deletion in publication_deletions)
                for entity_name in deleted_entity_names
            }
        )

        _, fundingrequest_deletions = super().delete(*args, **kwargs)
        counted_deletions = {
            key: counted_deletions.get(key, 0) + fundingrequest_deletions.get(key, 0)
            for key in set(counted_deletions) | set(fundingrequest_deletions)
        }

        return (sum(counted_deletions.values()), counted_deletions)


class FundingRequest(models.Model):
    objects = FundingRequestQuerySet.as_manager()

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
    request_date = models.DateField()
    request_number = models.CharField(max_length=20)

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
    publication = models.OneToOneField(
        Publication, on_delete=models.CASCADE, related_name="fundingrequest"
    )

    request_remarks = models.TextField(blank=True)

    review = models.OneToOneField(
        "FundingRequestReview", on_delete=models.CASCADE, related_name="fundingrequest"
    )

    legacy_request_id = models.CharField(max_length=255, blank=True)

    def get_absolute_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.pk})

    def delete(
        self, using: Any | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        if self.publication:
            self.publication.delete()
        return super().delete(using, keep_parents)
