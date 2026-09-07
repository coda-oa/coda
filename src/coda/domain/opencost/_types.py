"""Basic type definitions for OpenCost domain models."""
from enum import Enum
from typing import Annotated
from pydantic import StringConstraints


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
Currency = Annotated[str, StringConstraints(pattern=r"[A-Z]{3}")]
DateFormat = Annotated[str, StringConstraints(pattern=r"[0-9]{4}(-[0-9]{2}){0,2}")]


class ContractCostType(Enum):
    """OpenCost contract_cost_type"""
    publish = "publish"
    read = "read"
    publish_and_read = "publish and read"
    service_fee = "service fee"
    vat = "vat"


class PublicationCostType(Enum):
    """OpenCost publication_cost_type"""
    gold_oa = "gold-oa"
    vat = "vat"
    colour_charge = "colour charge"
    cover_charge = "cover charge"
    hybrid_oa = "hybrid-oa"
    other = "other"
    page_charge = "page charge"
    permission = "permission"
    publication_charge = "publication charge"
    reprint = "reprint"
    submission_fee = "submission fee"
    payment_fee = "payment fee"
