from dataclasses import dataclass


@dataclass
class FundingRequestReference:
    request_id: str
    url: str
