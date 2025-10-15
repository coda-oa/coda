from typing import cast

from coda.apps.invoices.models import FundingSource
from coda.domain.author import InstitutionId
from coda.domain.funding_sources import Budget, SplitSource
from coda.domain.invoice import FundingSourceId
from coda.domain.string import NonEmptyStr


def get_by_id(id: FundingSourceId) -> Budget | SplitSource:
    model = FundingSource.objects.get(pk=id)
    if model.type == "budget":
        return Budget(FundingSourceId(model.pk), NonEmptyStr(model.name))
    elif model.type == "institution":
        return SplitSource(
            FundingSourceId(model.pk),
            cast(InstitutionId, model.institution_id),
            NonEmptyStr(model.name),
        )

    raise ValueError("Invalid model type")


def create(source: Budget | SplitSource) -> FundingSourceId:
    if isinstance(source, Budget):
        type = "budget"
        institution_id = None
    elif isinstance(source, SplitSource):
        type = "institution"
        institution_id = source.institution
        existing = FundingSource.objects.filter(institution_id=source.institution).first()
        if existing:
            return FundingSourceId(existing.pk)

    model = FundingSource.objects.create(type=type, name=source.name, institution_id=institution_id)
    return FundingSourceId(model.pk)
