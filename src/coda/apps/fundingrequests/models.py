from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from coda.apps.fundingrequests.queryset import FundingRequestManager
from coda.apps.publications.models import Publication
from coda.domain.fundingrequest import PaymentMethod, links
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication.links import Link


class FundingRequestContact(models.Model):
    name = models.CharField()
    email = models.EmailField()

    def __str__(self) -> str:
        return self.name


class FundingOrganizationManager(models.Manager["FundingOrganization"]):
    def get_queryset(self) -> models.QuerySet["FundingOrganization"]:
        return super().get_queryset().filter(archived_at__isnull=True)

    def bulk_get_or_create_by_name(self, names: Iterable[str]) -> dict[str, "FundingOrganization"]:
        """Bulk get-or-create organizations by name.

        Returns a ``{name: organization}`` dict for all given names,
        creating any that don't already exist.
        """
        names_list = list(names)
        existing = {e.name: e for e in self.filter(name__in=names_list).only("pk", "name")}
        to_create = set(names_list) - existing.keys()
        created = self.bulk_create(self.model(name=n) for n in to_create)
        return existing | {org.name: org for org in created}


class FundingOrganization(models.Model):
    name = models.CharField()
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects: FundingOrganizationManager = (
        FundingOrganizationManager()
    )  # pyright: ignore[reportIncompatibleVariableOverride]
    all_objects = models.Manager()

    def __str__(self) -> str:
        return self.name

    def archive(self, *, when: datetime | None = None) -> None:
        if self.archived_at:
            raise ValueError("Funding organization is already archived")
        self.archived_at = when or timezone.now()
        self.save(update_fields=["archived_at"])

    def restore(self) -> None:
        if not self.archived_at:
            raise ValueError("Funding organization is not archived")
        self.archived_at = None
        self.save(update_fields=["archived_at"])

    def get_links(self) -> list[Link]:
        return [links.create_link(link.type.name, link.value) for link in self.links.all()]

    def set_links(self, links: Iterable[Link]) -> None:
        """Replace all links with domain Link objects.

        Clears existing links and creates new ``FundingOrganizationLink``
        instances from the provided domain ``Link`` protocol objects.

        Only link types with a corresponding ``FundingOrganizationLinkType``
        row are persisted; unknown types are silently skipped.
        """
        links_list = list(links)

        link_types = FundingOrganizationLinkType.objects.as_name_map()

        self.links.all().delete()

        new_links = [
            FundingOrganizationLink(
                type=link_types[link.type()],
                value=link.value(),
                funding_organization=self,
            )
            for link in links_list
            if link.type() in link_types
        ]
        FundingOrganizationLink.objects.bulk_create(new_links)


class FundingOrganizationLinkTypeManager(models.Manager["FundingOrganizationLinkType"]):
    def as_name_map(self) -> dict[str, "FundingOrganizationLinkType"]:
        """Return a ``{name: link_type}`` dict for all supported link types.

        The set of supported types is defined by ``link_types()`` in the domain
        layer, ensuring a single source of truth.
        """
        return {lt.name: lt for lt in self.filter(name__in=links.link_types())}


class FundingOrganizationLinkType(models.Model):
    name = models.CharField(max_length=255, unique=True)

    objects: FundingOrganizationLinkTypeManager = (
        FundingOrganizationLinkTypeManager()
    )  # pyright: ignore[reportIncompatibleVariableOverride]

    def __str__(self) -> str:
        return self.name


class FundingOrganizationLinkManager(models.Manager["FundingOrganizationLink"]):
    def find_by_links(self, links: Iterable[Link]) -> models.QuerySet["FundingOrganizationLink"]:
        """Find existing links matching any of the given domain Link objects."""
        return self.filter(
            type__name__in={link.type() for link in links},
            value__in=[link.value() for link in links],
        ).select_related("funding_organization")


class FundingOrganizationLink(models.Model):
    type = models.ForeignKey(FundingOrganizationLinkType, on_delete=models.CASCADE)
    value = models.TextField()
    funding_organization = models.ForeignKey(
        FundingOrganization, on_delete=models.CASCADE, related_name="links"
    )

    objects: FundingOrganizationLinkManager = (
        FundingOrganizationLinkManager()
    )  # pyright: ignore[reportIncompatibleVariableOverride]


class ExternalFunding(models.Model):
    funding_request = models.ForeignKey(
        "FundingRequest",
        on_delete=models.CASCADE,
        related_name="external_funding",
        null=True,
    )
    organization = models.ForeignKey(FundingOrganization, on_delete=models.PROTECT)
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
    objects: FundingRequestManager = (
        FundingRequestManager()
    )  # pyright: ignore[reportIncompatibleVariableOverride]

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

    external_costsplitting = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text="True if cost splitting occurred, None/null if unknown (omitted in OpenCost)",
    )

    def get_absolute_url(self) -> str:
        return reverse("fundingrequests:detail", kwargs={"pk": self.pk})

    def delete(
        self, using: Any | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        if self.publication:
            self.publication.delete()
        return super().delete(using, keep_parents)
