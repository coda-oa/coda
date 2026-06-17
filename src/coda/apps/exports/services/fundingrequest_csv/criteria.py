from dataclasses import dataclass

from django.db.models import Q

from coda.domain.finance.invoice import FundingSourceId


@dataclass
class InvoiceFundingSourceCriteria:
    funding_source: FundingSourceId

    def _to_query(self) -> Q:
        return Q(publication__position__funding_assignments__funding_source=self.funding_source)
