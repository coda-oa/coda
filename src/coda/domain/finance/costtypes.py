import enum


class PublicationCostType(enum.Enum):
    """
    Enum representing the cost type based on the OpenCost schema.
    """

    Gold_OA = "gold-oa"
    Hybrid_OA = "hybrid-oa"
    Vat = "vat"
    Cover_Charge = "cover charge"
    Colour_Charge = "colour charge"
    Page_Charge = "page charge"
    Permission = "permission"
    Publication_Charge = "publication charge"
    Reprint = "reprint"
    Submission_Fee = "submission fee"
    Payment_Fee = "payment fee"
    Other = "other"

    def is_vat(self) -> bool:
        return self == PublicationCostType.Vat


class ContractCostType(enum.Enum):
    """
    Enum representing the cost type for contracts based on the OpenCost schema.
    """

    Publish = "publish"
    Read = "read"
    Publish_And_Read = "publish and read"
    Service_Fee = "service fee"
    Vat = "vat"

    def is_vat(self) -> bool:
        return self == ContractCostType.Vat


CostType = PublicationCostType | ContractCostType
