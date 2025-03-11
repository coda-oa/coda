from collections.abc import Callable
from typing import Any, cast

import pytest

from coda.checks.checkfactory import CheckFactory
from coda.apps.fundingrequests.services import checks, fundingrequests
from coda.checks.checklist import CheckResult, CheckRun, CheckSuccessful
from coda.fundingrequest import FundingRequest, TPublication
from coda.publication import Monograph, Publication
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder


class PublicationCheckSpy:
    name = "Publication type check"
    params: dict[str, Any] = {}

    @property
    def description(self) -> str:
        return "Check if publication type is valid"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Publication)
        return CheckSuccessful()


class MonographCheckSpy:
    name = "Monograph check"
    params: dict[str, Any] = {}

    @property
    def description(self) -> str:
        return "Check if publication type is monograph"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Monograph)
        return CheckSuccessful()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("get_builder", "expected_check_name"),
    [
        (lambda: ArticleRequestDataBuilder(), PublicationCheckSpy.name),
        (lambda: MonographRequestDataBuilder(), MonographCheckSpy.name),
    ],
)
def test__given_fundingrequest__run_checks__runs_checks_for_publication_type(
    get_builder: Callable[[], ArticleRequestDataBuilder | MonographRequestDataBuilder],
    expected_check_name: str,
) -> None:
    builder = get_builder()
    fundingrequest_id = fundingrequests.create_fundingrequest(
        builder.publication_dto(),
        builder.cost_dto(),
        builder.external_funding_dto(),
        builder.extra_information_dto(),
    )

    checkfactory = CheckFactory()
    checkfactory.register(Publication, PublicationCheckSpy)
    checkfactory.register(Monograph, MonographCheckSpy)

    checkruns = checks.run_checks(fundingrequest_id, checkfactory=checkfactory)

    checkruns_casted = cast(list[CheckRun], list(checkruns))
    assert len(checkruns_casted) == 1

    actual_check, *_ = checkruns_casted
    assert actual_check.check.name == expected_check_name


@pytest.mark.django_db
def test__creating_fundingrequest__runs_checks() -> None:
    checkfactory = CheckFactory()
    checkfactory.register(Publication, PublicationCheckSpy)
    builder = ArticleRequestDataBuilder()

    new_id = fundingrequests.create_fundingrequest(
        builder.publication_dto(),
        builder.cost_dto(),
        builder.external_funding_dto(),
        builder.extra_information_dto(),
        checkfactory=checkfactory,
    )

    checkruns = checks.get_checkrun(new_id, checkfactory=checkfactory)
    assert checkruns is not None

    checkruns_casted = cast(list[CheckRun], list(checkruns))
    assert len(checkruns_casted) == 1

    actual_check, *_ = checkruns_casted
    assert actual_check.check.name == PublicationCheckSpy.name
