from coda.apps.checklist.models import CheckRun as CheckRunModel
from coda.checks.checkfactory import CheckFactory
from coda.checks.checklist import CheckFailed, CheckResult, CheckRun, CheckSuccessful, CheckWarning
from coda.domain.fundingrequest import FundingRequestId


def as_domain_object(checkrun_model: CheckRunModel, checkfactory: CheckFactory) -> CheckRun:
    result = _map_str_to_result(
        checkrun_model.result, checkrun_model.message, checkrun_model.result_data
    )
    check = checkfactory.create(checkrun_model.check_name)
    check.params = checkrun_model.check_parameters

    return CheckRun(
        check=check,
        result=result,
        timestamp=checkrun_model.timestamp,
        fundingrequest=FundingRequestId(checkrun_model.fundingrequest.pk),
    )


def as_django_model(checkrun: CheckRun) -> CheckRunModel:
    data = checkrun.result.data if isinstance(checkrun.result, CheckSuccessful) else {}
    result_type = _map_result_to_str(checkrun)

    return CheckRunModel(
        fundingrequest_id=checkrun.fundingrequest,
        check_name=checkrun.check.__class__.__name__,
        check_parameters=checkrun.check.params,
        result=result_type,
        result_data=data,
        message=checkrun.result.message,
        timestamp=checkrun.timestamp,
    )


def _map_result_to_str(checkrun: CheckRun) -> str:
    result_type_to_str = {
        CheckSuccessful: "success",
        CheckFailed: "failure",
        CheckWarning: "warning",
    }
    return result_type_to_str[type(checkrun.result)]


def _map_str_to_result(result_str: str, message: str, data: dict[str, str | int]) -> CheckResult:
    str_to_result_type: dict[str, type[CheckResult]] = {
        "success": CheckSuccessful,
        "failure": CheckFailed,
        "warning": CheckWarning,
    }

    result_type = str_to_result_type[result_str]
    if result_type is CheckSuccessful:
        return CheckSuccessful(message=message, data=data)

    return result_type(message=message)
