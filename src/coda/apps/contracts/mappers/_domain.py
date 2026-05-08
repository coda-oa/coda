from django.db.models import Model, QuerySet

from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.mappers import prefixed
from coda.domain.contract import Contract, ContractId, PublicationBilling, PublisherId
from coda.domain.date import DateRange
from coda.domain.publication.publication import JournalId
from coda.domain.string import NonEmptyStr
from coda.coda_itertools import LazyCachedIterable


class ContractDomainMapper:
    @staticmethod
    def prefetch[_T: Model](qs: QuerySet[_T], prefix: str = "") -> QuerySet[_T]:
        return qs.prefetch_related(
            prefixed(prefix, "publishers"),
            prefixed(prefix, "journals"),
        )

    @staticmethod
    def map(model: ContractModel) -> Contract:
        return Contract(
            id=ContractId(model.pk),
            name=NonEmptyStr(model.name),
            publishers=LazyCachedIterable(PublisherId(p.pk) for p in model.publishers.all()),
            journals=LazyCachedIterable(JournalId(j.pk) for j in model.journals.all()),
            period=DateRange.create(start=model.start_date, end=model.end_date),
            publication_billing=PublicationBilling(model.publication_billing),
        )
