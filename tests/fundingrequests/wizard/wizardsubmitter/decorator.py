from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Generic, cast

import pytest
from django.test import Client

from coda.fundingrequest import FundingRequestId
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder

from .wizardsubmitter import TDataBuilder, WizardSubmitter

CreationWizardSubmitterFactory = Callable[[Client, TDataBuilder], WizardSubmitter]
UpdateWizardSubmitterFactory = Callable[[Client, FundingRequestId, TDataBuilder], WizardSubmitter]
AnyWizardSubmitterFactory = (
    CreationWizardSubmitterFactory[TDataBuilder] | UpdateWizardSubmitterFactory[TDataBuilder]
)
BuilderFactory = Callable[[], TDataBuilder]


@dataclass
class DistinctWizardSubmitters:
    article: AnyWizardSubmitterFactory[ArticleRequestDataBuilder]
    monograph: AnyWizardSubmitterFactory[MonographRequestDataBuilder]


@dataclass
class DistinctExtraArgs:
    article: dict[str, Any] = field(default_factory=dict)
    monograph: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not tuple(self.article.keys()) == tuple(self.monograph.keys()):
            raise ValueError("Argnames must be the same for both article and monograph")

    def keys(self) -> list[str]:
        return list(self.article.keys())


class UseWizardSubmitter(Generic[TDataBuilder]):
    """
    A decorator class for parameterizing test functions with different wizard submitters and builders.

    This class allows you to create test functions that are parameterized with different combinations
    of wizard submitters and data builders for articles and monographs. It supports both distinct
    submitters for articles and monographs, as well as a singular submitter for both.
    """

    @classmethod
    def distinct(
        cls,
        article: AnyWizardSubmitterFactory[ArticleRequestDataBuilder],
        monograph: AnyWizardSubmitterFactory[MonographRequestDataBuilder],
        *,
        article_builders: Iterable[BuilderFactory[ArticleRequestDataBuilder]] = (),
        monograph_builders: Iterable[BuilderFactory[MonographRequestDataBuilder]] = (),
        article_args: dict[str, Any] | None = None,
        monograph_args: dict[str, Any] | None = None,
    ) -> "UseWizardSubmitter[TDataBuilder]":
        """
        Creates a `UseWizardSubmitter` instance with distinct article and monograph submitters,
        along with their respective builders and arguments.

        Args:
            article (AnyWizardSubmitterFactory[ArticleRequestDataBuilder]): The article submitter factory.
            monograph (AnyWizardSubmitterFactory[MonographRequestDataBuilder]): The monograph submitter factory.
            article_builders (Iterable[BuilderFactory[ArticleRequestDataBuilder]], optional): An iterable of article builder factories. Defaults to an empty tuple.
            monograph_builders (Iterable[BuilderFactory[MonographRequestDataBuilder]], optional): An iterable of monograph builder factories. Defaults to an empty tuple.
            article_args (dict[str, Any], optional): A dictionary of additional arguments for the article submitter. Defaults to None.
            monograph_args (dict[str, Any], optional): A dictionary of additional arguments for the monograph submitter. Defaults to None.

        Returns:
            UseWizardSubmitter[TDataBuilder]: An instance of `UseWizardSubmitter` configured with distinct submitters and extra arguments.
        """
        return cls(
            DistinctWizardSubmitters(article, monograph),
            article_builders=article_builders,
            monograph_builders=monograph_builders,
            extraargs=DistinctExtraArgs(article_args or {}, monograph_args or {}),
        )

    @classmethod
    def singular(
        cls,
        submitter: AnyWizardSubmitterFactory[TDataBuilder],
        *,
        article_builders: Iterable[BuilderFactory[ArticleRequestDataBuilder]] = (),
        monograph_builders: Iterable[BuilderFactory[MonographRequestDataBuilder]] = (),
        **kwargs: Any,
    ) -> "UseWizardSubmitter[TDataBuilder]":
        """
        Creates an instance of UseWizardSubmitter with a single provided submitter and optional builders.

        Args:
            submitter (AnyWizardSubmitterFactory[TDataBuilder]): The submitter factory to be used.
            article_builders (Iterable[BuilderFactory[ArticleRequestDataBuilder]], optional): An iterable of article request data builder factories. Defaults to an empty tuple.
            monograph_builders (Iterable[BuilderFactory[MonographRequestDataBuilder]], optional): An iterable of monograph request data builder factories. Defaults to an empty tuple.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            UseWizardSubmitter[TDataBuilder]: An instance of UseWizardSubmitter with the provided submitter and builders.
        """
        return cls(
            DistinctWizardSubmitters(submitter, submitter),  # type: ignore
            article_builders=article_builders,
            monograph_builders=monograph_builders,
            extraargs=kwargs,
        )

    def __init__(
        self,
        submitter: DistinctWizardSubmitters,
        article_builders: Iterable[BuilderFactory[ArticleRequestDataBuilder]] = (),
        monograph_builders: Iterable[BuilderFactory[MonographRequestDataBuilder]] = (),
        extraargs: dict[str, Any] | DistinctExtraArgs | None = None,
    ) -> None:
        self.submitter = submitter
        self.article_builders = article_builders or [ArticleRequestDataBuilder]
        self.monograph_builders = monograph_builders or [MonographRequestDataBuilder]

        if extraargs is None:
            self.extraargs = DistinctExtraArgs()
        elif not isinstance(extraargs, DistinctExtraArgs):
            self.extraargs = DistinctExtraArgs(article=extraargs, monograph=extraargs)
        else:
            self.extraargs = extraargs

    def __call__(self, test_fn: Callable[..., None]) -> Callable[..., None]:
        @pytest.mark.parametrize(
            ("get_builder", "get_wizard", "kwargs"),
            [
                *(
                    (builder, self.submitter.article, self.extraargs.article)
                    for builder in self.article_builders
                ),
                *(
                    (builder, self.submitter.monograph, self.extraargs.monograph)
                    for builder in self.monograph_builders
                ),
            ],
        )
        def _wrapper(
            client: Client,
            get_builder: BuilderFactory[TDataBuilder],
            get_wizard: AnyWizardSubmitterFactory[TDataBuilder],
            kwargs: dict[str, Any],
        ) -> None:
            test_fn(client, get_builder, get_wizard, **kwargs)

        return cast(Callable[..., None], _wrapper)
