"""Mapper functions for ExternalFunding domain objects."""

from collections.abc import Iterable

from coda.apps.fundingrequests import models as fundingrequest_models
from coda.domain.fundingrequest import AnyFundingRequest, ExternalFunding


def as_django_models(
    fr_id: int, funding: Iterable[ExternalFunding]
) -> list[fundingrequest_models.ExternalFunding]:
    """Map domain ExternalFunding to ExternalFunding model instances (API-consistent alias)."""
    return [
        fundingrequest_models.ExternalFunding(
            funding_request_id=fr_id,
            organization_id=ef.organization,
            project_id=ef.project_id,
            project_name=ef.project_name,
        )
        for ef in funding
    ]


def synchronize_external_funding_relationship(
    fr: fundingrequest_models.FundingRequest, funding: Iterable[ExternalFunding]
) -> None:
    """Synchronize external funding relationship by replacing all records."""
    fr.external_funding.all().delete()

    if funding:
        fundingrequest_models.ExternalFunding.objects.bulk_create(as_django_models(fr.pk, funding))


def bulk_create_for_model(
    fr: fundingrequest_models.FundingRequest, funding: Iterable[ExternalFunding]
) -> None:
    """Bulk create external funding records for a funding request (with deletion logic)."""
    synchronize_external_funding_relationship(fr, funding)


def create_bulk_models(
    fundingrequests: Iterable[AnyFundingRequest],
    created_frs: Iterable[fundingrequest_models.FundingRequest],
) -> list[fundingrequest_models.ExternalFunding]:
    """Create ExternalFundingModel instances for bulk creation."""
    external_funding_objs = []
    for fundingrequest, fr in zip(fundingrequests, created_frs):
        for ef in fundingrequest.external_funding:
            external_funding_objs.append(
                fundingrequest_models.ExternalFunding(
                    funding_request_id=fr.pk,
                    organization_id=ef.organization,
                    project_id=ef.project_id,
                    project_name=ef.project_name,
                )
            )
    return external_funding_objs
