from collections.abc import Iterable

from django.db.models import QuerySet

from coda.apps.checklist import mapper
from coda.apps.checklist.models import CheckRun as CheckRunModel
from coda.checks.checkfactory import CheckFactory
from coda.checks.checklist import CheckRun
from coda.domain.fundingrequest import FundingRequestId


def save(checkrun: Iterable[CheckRun]) -> None:
    first_check = next(iter(checkrun), None)
    if first_check is not None:
        _get_by_fundingrequest_id(first_check.fundingrequest).delete()

    CheckRunModel.objects.bulk_create([mapper.as_django_model(check) for check in checkrun])


def get(
    fundingrequest_id: FundingRequestId,
    restoring_checkfactory: CheckFactory,
) -> Iterable[CheckRun]:
    return tuple(
        mapper.as_domain_object(checkrun, restoring_checkfactory)
        for checkrun in _get_by_fundingrequest_id(fundingrequest_id)
    )


def _get_by_fundingrequest_id(fundingrequest_id: FundingRequestId) -> QuerySet[CheckRunModel]:
    return CheckRunModel.objects.filter(fundingrequest=fundingrequest_id.pk)
