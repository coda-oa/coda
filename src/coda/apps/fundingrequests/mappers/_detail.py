from django.db.models import QuerySet

from coda.apps.fundingrequests.mappers._domain import FundingRequestDomainMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.domain.fundingrequest import AnyFundingRequest


class FundingRequestDetailMapper:
    @staticmethod
    def prefetch(
        qs: QuerySet[FundingRequestModel], prefix: str = ""
    ) -> QuerySet[FundingRequestModel]:
        return FundingRequestDomainMapper.prefetch(qs, prefix=prefix).prefetch_related("labels")

    @staticmethod
    def map(model: FundingRequestModel) -> AnyFundingRequest:
        return FundingRequestDomainMapper.map(model)
