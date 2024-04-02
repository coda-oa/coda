from typing import TypedDict


class CostDto(TypedDict):
    estimated_cost: float
    estimated_cost_currency: str


class ExternalFundingDto(TypedDict):
    organization: int
    project_id: str
    project_name: str
