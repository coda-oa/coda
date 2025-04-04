from coda.apps.checklist import repository as checklist_repository
from coda.apps.checklist.services import get_checkfactory
from coda.apps.fundingrequests import repository
from coda.checks.checkfactory import CheckFactory
from coda.checks.checklist import ChecklistRun
from coda.domain.fundingrequest import FundingRequestId


def run_checks(
    fundingrequest_id: FundingRequestId,
    *,
    checkfactory: CheckFactory | None = None,
) -> ChecklistRun:
    checkfactory = checkfactory or get_checkfactory()
    fr = repository.get_by_id(fundingrequest_id)
    checks = checkfactory.checks_for(type(fr.publication))
    checklistrun = checks.run(fr)  # type: ignore
    checklist_repository.save(checklistrun)
    return checklistrun


def get_checkrun(
    fundingrequest_id: FundingRequestId,
    *,
    checkfactory: CheckFactory | None = None,
) -> ChecklistRun | None:
    checkfactory = checkfactory or get_checkfactory()
    checklistrun = checklist_repository.get(fundingrequest_id, checkfactory)
    if not checklistrun:
        return None

    first_timestamp = tuple(checklistrun)[0].timestamp
    return ChecklistRun(fundingrequest_id, timestamp=first_timestamp, checkruns=checklistrun)
