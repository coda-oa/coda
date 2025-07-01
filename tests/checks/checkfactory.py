from coda.checks.checkfactory import CheckFactoryImpl
from coda.checks.checklist import CheckResult, CheckSuccessful
from coda.domain.fundingrequest import FundingRequest, TPublication
from coda.domain.publication import Monograph, Publication


class DummyCheck:
    params: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "DummyCheck"

    @property
    def description(self) -> str:
        return "Dummy check description"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        return CheckSuccessful()


checkfactory = CheckFactoryImpl()
checkfactory.register(Publication, DummyCheck)
checkfactory.register(Monograph, DummyCheck)
