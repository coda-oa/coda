from collections.abc import Callable, Iterable
from typing import Any, TypeVar, cast

from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

from coda.domain.fundingrequest import FundingRequestId
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.fundingrequests.wizard.stepdata import (
    extra_information_step,
    funding_step,
    journal_contract_step,
    publication_step,
    publisher_contract_step,
)
from tests.test_wizard import complete_early, next

TDataBuilder = TypeVar("TDataBuilder", ArticleRequestDataBuilder, MonographRequestDataBuilder)
StepDataFactory = Callable[[], dict[str, Any]]
StepIterationStrategy = Callable[[list[StepDataFactory]], Iterable[dict[str, Any]]]


def post_data_iterator(steps: list[StepDataFactory]) -> Iterable[dict[str, Any]]:
    for step in steps:
        yield next() | step()


def complete_early_iterator(until: int = -1) -> StepIterationStrategy:
    """
    Creates an iterator that yields steps up to, but not including, the specified index and then yields the step at the specified index with the complete early message.

    Args:
        until (int): The index up to which steps should be yielded. Defaults to -1, which means all steps are yielded.

    Returns:
        StepIterationStrategy: A function that takes a list of StepDataFactory objects and yields dictionaries.
    """

    def _complete_early_iterator(steps: list[StepDataFactory]) -> Iterable[dict[str, Any]]:
        for step in steps[:until]:
            yield next() | step()

        step = steps[until]
        yield complete_early() | step()

    return _complete_early_iterator


class WizardSubmitter:
    """
    A class to automate the submission of a series of steps in a wizard-like form.

    Attributes:
        step_iterator (StepIterationStrategy): A strategy for iterating over the steps. Defaults to post_data_iterator.

    Methods:
        submit_all() -> HttpResponse:
            Submits all steps in the wizard form and returns the final HTTP response.

        goto_initial_page() -> None:
            Navigates to the initial page of the wizard form.

        submit_step(data: dict[str, Any]) -> HttpResponse:
            Submits a single step in the wizard form and returns the HTTP response.
    """

    def __init__(
        self,
        client: Client,
        url: str,
        steps: list[StepDataFactory],
        step_iterator: StepIterationStrategy = post_data_iterator,
    ) -> None:
        self.url = url
        self.steps = steps
        self.client = client
        self.step_iterator = step_iterator

    def submit_all(self) -> HttpResponse:
        self.goto_initial_page()

        if not self.steps:
            raise ValueError("No steps provided")

        response: HttpResponse
        for step in self.step_iterator(self.steps):
            response = self.submit_step(step)

        return response

    def goto_initial_page(self) -> None:
        _ = self.client.get(self.url)

    def submit_step(self, data: dict[str, Any]) -> HttpResponse:
        return cast(HttpResponse, self.client.post(self.url, data))


def article_wizardsubmitter(
    client: Client, data_builder: ArticleRequestDataBuilder
) -> WizardSubmitter:
    url = reverse("fundingrequests:create_wizard")
    return WizardSubmitter(
        client,
        url,
        [
            lambda: journal_contract_step.stepdata(data_builder.publication_dto()),
            lambda: publication_step.stepdata(data_builder.publication_dto()),
            lambda: funding_step.stepdata(
                data_builder.cost_dto(), data_builder.external_funding_dto()
            ),
            lambda: extra_information_step.stepdata(data_builder.extra_information_dto()),
        ],
    )


def monograph_wizardsubmitter(
    client: Client, data_builder: MonographRequestDataBuilder
) -> WizardSubmitter:
    url = reverse("fundingrequests:create_monograph")

    return WizardSubmitter(
        client,
        url,
        [
            lambda: publisher_contract_step.stepdata(data_builder.publication_dto()),
            lambda: publication_step.stepdata(data_builder.publication_dto()),
            lambda: funding_step.stepdata(
                data_builder.cost_dto(), data_builder.external_funding_dto()
            ),
            lambda: extra_information_step.stepdata(data_builder.extra_information_dto()),
        ],
    )


def update_extra_information_wizard(
    client: Client,
    fundingrequest_id: FundingRequestId,
    data_builder: TDataBuilder,
) -> WizardSubmitter:
    url = reverse("fundingrequests:update_submitter", kwargs={"pk": fundingrequest_id})

    return WizardSubmitter(
        client,
        url,
        [lambda: extra_information_step.stepdata(data_builder.extra_information_dto())],
    )


def update_article_publication_wizard(
    client: Client,
    fundingrequest_id: FundingRequestId,
    data_builder: ArticleRequestDataBuilder,
) -> WizardSubmitter:
    url = reverse("fundingrequests:update_publication", kwargs={"pk": fundingrequest_id})

    return WizardSubmitter(
        client,
        url,
        [
            lambda: publication_step.stepdata(data_builder.publication_dto()),
            lambda: journal_contract_step.stepdata(data_builder.publication_dto()),
        ],
    )


def update_monograph_publication_wizard(
    client: Client,
    fundingrequest_id: FundingRequestId,
    data_builder: MonographRequestDataBuilder,
) -> WizardSubmitter:
    url = reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fundingrequest_id})

    return WizardSubmitter(
        client,
        url,
        [
            lambda: publication_step.stepdata(data_builder.publication_dto()),
            lambda: publisher_contract_step.stepdata(data_builder.publication_dto()),
        ],
    )


def update_funding_wizard(
    client: Client,
    fundingrequest_id: FundingRequestId,
    data_builder: TDataBuilder,
) -> WizardSubmitter:
    url = reverse("fundingrequests:update_funding", kwargs={"pk": fundingrequest_id})

    return WizardSubmitter(
        client,
        url,
        [
            lambda: funding_step.stepdata(
                data_builder.cost_dto(), data_builder.external_funding_dto()
            ),
        ],
    )
