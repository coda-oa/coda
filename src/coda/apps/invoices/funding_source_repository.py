from collections.abc import Iterable
from typing import Literal, cast

from coda.apps.invoices import mapper as invoice_mapper
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, FundingSource, SplitSource
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.string import NonEmptyStr


class FundingSourceNotFound(ValueError):
    def __init__(self, id: int | None = None, name: str = "") -> None:
        if id:
            msg = f"FundingSource with {id=} does not exist"
        elif name:
            msg = f"FundingSource with {name=} does not exist"
        else:
            msg = "FundingSource not found"

        super().__init__(msg)


def get_by_id(id: FundingSourceId) -> FundingSource:
    try:
        model = FundingSourceModel.objects.get(pk=id)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(id) from e

    return invoice_mapper.as_domain_funding_source(model)


def get_by_institution(id: InstitutionId) -> SplitSource:
    try:
        model = FundingSourceModel.objects.get(institution_id=id)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(id) from e

    return SplitSource(FundingSourceId(model.pk), id, NonEmptyStr(model.name))


def get_by_name(name: str) -> FundingSource:
    try:
        model = FundingSourceModel.objects.get(name=name)
    except FundingSourceModel.DoesNotExist as e:
        raise FundingSourceNotFound(name=name) from e

    return invoice_mapper.as_domain_funding_source(model)


def create(source: FundingSource) -> FundingSourceId:
    if isinstance(source, Budget):
        type = "budget"
        institution_id = None
    elif isinstance(source, SplitSource):
        type = "institution"
        institution_id = source.institution
        existing = FundingSourceModel.objects.filter(institution_id=source.institution).first()
        if existing:
            return FundingSourceId(existing.pk)

    model = FundingSourceModel.objects.create(
        type=type, name=source.name, institution_id=institution_id
    )
    return FundingSourceId(model.pk)


def types_for(
    ids: Iterable[FundingSourceId],
) -> dict[FundingSourceId, Literal["budget", "institution"]]:
    fs = FundingSourceModel.objects.filter(pk__in=ids).values_list("pk", "type")
    return {FundingSourceId(pk): cast(Literal["budget", "institution"], t) for pk, t in fs}
