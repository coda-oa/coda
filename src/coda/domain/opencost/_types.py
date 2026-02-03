"""Basic type definitions for OpenCost domain models.

This module contains simple type aliases and enums that don't depend on other OpenCost modules,
preventing circular import issues.
"""

from enum import Enum
from typing import Annotated
from pydantic import StringConstraints


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
Currency = Annotated[str, StringConstraints(pattern=r"[A-Z]{3}")]
DateFormat = Annotated[str, StringConstraints(pattern=r"[0-9]{4}(-[0-9]{2}){0,2}")]


class ContractCostType(Enum):
    publish = "publish"
    read = "read"
    vat = "vat"


class PublicationCostType(Enum):
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
