from collections.abc import Iterable

from django.db.models import QuerySet

from coda.apps.checklist.models import CheckRun as CheckRunModel
from coda.checks.checkfactory import CheckFactory
from coda.checks.checklist import CheckFailed, CheckResult, CheckRun, CheckSuccessful, CheckWarning
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
    data = check.result.data if isinstance(check.result, CheckSuccessful) else {}
    result_type = _map_result_to_str(check)
    return CheckRunModel(
        fundingrequest_id=check.fundingrequest,
        check_name=check.check.__class__.__name__,
        check_parameters=check.check.params,
        result=result_type,
        result_data=data,
        message=check.result.message,
        timestamp=check.timestamp,
    )


def _map_result_to_str(checkrun: CheckRun) -> str:
    result_type_to_str = {
        CheckSuccessful: "success",
        CheckFailed: "failure",
        CheckWarning: "warning",
    }

    return result_type_to_str[type(checkrun.result)]


def _restore_checkrun(
    checkrun_model: CheckRunModel, restoring_checkfactory: CheckFactory
) -> CheckRun:
    result = _map_to_result(checkrun_model)
    check = restoring_checkfactory.create(checkrun_model.check_name)
    checkrun = CheckRun(
        check=check,
        result=result,
        timestamp=checkrun_model.timestamp,
        fundingrequest=FundingRequestId(checkrun_model.fundingrequest_id),
    )
    checkrun.check.params = checkrun_model.check_parameters
    return checkrun


def _map_to_result(checkrun_model: CheckRunModel) -> CheckResult:
    str_to_result_type: dict[str, type[CheckResult]] = {
        "success": CheckSuccessful,
        "failure": CheckFailed,
        "warning": CheckWarning,
    }

    result_type = str_to_result_type[checkrun_model.result]
    if result_type is CheckSuccessful:
        return CheckSuccessful(message=checkrun_model.message, data=checkrun_model.result_data)

    return result_type(message=checkrun_model.message)
