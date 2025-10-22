import enum

from coda.domain.contract import ContractYear
from coda.domain.publication.publication import PublicationId


class PublicationCostType(enum.Enum):
    """
    Enum representing the cost type based on the OpenCost schema.
    """

    Gold_OA = "gold-oa"
    Hybrid_OA = "hybrid-oa"
    Vat = "vat"
    Colour_Charge = "colour charge"
    Page_Charge = "page charge"
    Permission = "permission"
    Publication_Charge = "publication charge"
    Reprint = "reprint"
    Submission_Fee = "submission fee"
    Payment_Fee = "payment fee"
    Other = "other"


class ContractCostType(enum.Enum):
    """
    Enum representing the cost type for contracts based on the OpenCost schema.
    """

    Publish = "publish"
    Read = "read"
    Vat = "vat"


ItemType = PublicationId | ContractYear | str
CostType = PublicationCostType | ContractCostType
