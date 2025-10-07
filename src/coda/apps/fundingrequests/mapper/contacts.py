"""Mapper functions for FundingRequestContact domain objects."""

from collections.abc import Iterable

from coda.apps.fundingrequests import models as fundingrequest_models
from coda.domain.fundingrequest import AnyFundingRequest, FundingRequestContact


def as_django_model(contact: FundingRequestContact) -> fundingrequest_models.FundingRequestContact:
    """Create a new FundingRequestContact model from domain object (API-consistent alias)."""
    contact_model = fundingrequest_models.FundingRequestContact()
    contact_model.name = contact.name
    contact_model.email = contact.email
    return contact_model


def synchronize_contact_relationship(
    fr_model: fundingrequest_models.FundingRequest, contact: FundingRequestContact
) -> None:
    """Synchronize contact relationship with create/update/delete logic."""
    if not contact and not fr_model.extra_contact:
        return

    if not contact and fr_model.extra_contact:
        fr_model.extra_contact.delete()
        fr_model.extra_contact = None
        return

    extra_contact = as_django_model(contact)
    if fr_model.extra_contact:
        extra_contact.pk = fr_model.extra_contact.pk

    fr_model.extra_contact = extra_contact
    fr_model.extra_contact.save()


def create_bulk_models_and_map(
    fundingrequests: Iterable[AnyFundingRequest],
    created_frs: Iterable[fundingrequest_models.FundingRequest],
) -> tuple[
    list[fundingrequest_models.FundingRequestContact],
    dict[int, fundingrequest_models.FundingRequestContact],
]:
    """Create FundingRequestContactModel instances for bulk creation and return mapping."""
    contact_objs = []
    contact_map = {}  # Map FundingRequestModel.id to FundingRequestContactModel

    for fundingrequest, fr in zip(fundingrequests, created_frs):
        contact = fundingrequest.extra_contact
        if contact:
            contact_obj = as_django_model(contact)
            contact_objs.append(contact_obj)
            contact_map[fr.pk] = contact_obj

    return contact_objs, contact_map
