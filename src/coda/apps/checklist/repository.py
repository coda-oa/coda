from collections.abc import Iterable

from django.db.models import QuerySet

from coda.apps.checklist.models import CheckRun as CheckRunModel
from coda.checks.checkfactory import CheckFactory
from coda.checks.checklist import CheckFailed, CheckRun, CheckSuccessful
from coda.fundingrequest import FundingRequestId


def save(checkrun: Iterable[CheckRun]) -> None:
    first_check = next(iter(checkrun), None)
    if first_check is not None:
        _get_by_fundingrequest_id(first_check.fundingrequest).delete()

    CheckRunModel.objects.bulk_create([_to_checkrun_model(check) for check in checkrun])


def get(
    fundingrequest_id: FundingRequestId,
    restoring_checkfactory: CheckFactory,
) -> Iterable[CheckRun]:
    return tuple(
        _restore_checkrun(checkrun, restoring_checkfactory)
        for checkrun in _get_by_fundingrequest_id(fundingrequest_id)
    )


def _get_by_fundingrequest_id(fundingrequest_id: FundingRequestId) -> QuerySet[CheckRunModel]:
    return CheckRunModel.objects.filter(fundingrequest=fundingrequest_id)


def _to_checkrun_model(check: CheckRun) -> CheckRunModel:
    data = (
        check.result.data or {}
        if isinstance(check.result, CheckSuccessful)
        else {"reason": check.result.reason}
    )
    result_type = "success" if isinstance(check.result, CheckSuccessful) else "failure"
    return CheckRunModel(
        fundingrequest_id=check.fundingrequest,
        check_name=check.check.__class__.__name__,
        check_parameters=check.check.params,
        result=result_type,
        result_data=data,
        timestamp=check.timestamp,
    )


def _restore_checkrun(
    checkrun_model: CheckRunModel, restoring_checkfactory: CheckFactory
) -> CheckRun:
    result = (
        CheckSuccessful(checkrun_model.result_data)
        if checkrun_model.result == "success"
        else CheckFailed(checkrun_model.result_data["reason"])
    )

    check = restoring_checkfactory.create(checkrun_model.check_name)
    checkrun = CheckRun(
        check=check,
        result=result,
        timestamp=checkrun_model.timestamp,
        fundingrequest=FundingRequestId(checkrun_model.fundingrequest_id),
    )
    checkrun.check.params = checkrun_model.check_parameters
    return checkrun
