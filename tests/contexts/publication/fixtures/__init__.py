"""Test fixtures for publication context.

Re-exports metadata builders, sample fixtures, and funder data for clean imports:

    from tests.contexts.publication.fixtures import (
        NatureArticleScenario,
        SpringerBookScenario,
        article_metadata,
        book_metadata,
        NATURE_EISSN,
        NATURE_JOURNAL_TITLE,
        # Funder fixture data
        AUTHORS,
        DOI_WITH_FUNDERS,
        FUNDING,
        JOURNAL_EISSN,
        JOURNAL_PUBLISHER,
        JOURNAL_TITLE,
        LICENSE,
        PUBLICATION_STATE,
        TITLE,
    )
"""

from tests.contexts.publication.fixtures.sample_funded_article import (
    AUTHORS,
    DOI_WITH_FUNDERS,
    FUNDING,
    JOURNAL_EISSN,
    JOURNAL_PUBLISHER,
    JOURNAL_TITLE,
    LICENSE,
    PUBLICATION_STATE,
    TITLE,
    configure_funded_article_client,
    funded_article_metadata,
    FundedArticleScenario,
)
from tests.contexts.publication.fixtures.metadata import (
    NATURE_EISSN,
    NATURE_JOURNAL_TITLE,
    article_metadata,
    book_metadata,
)
from tests.contexts.publication.fixtures.sample_metadata import (
    ArticleScenario,
    BookScenario,
    NatureArticleScenario,
    SpringerBookScenario,
)

__all__ = [
    # Builders
    "NATURE_EISSN",
    "NATURE_JOURNAL_TITLE",
    "article_metadata",
    "book_metadata",
    # Samples
    "ArticleScenario",
    "BookScenario",
    "NatureArticleScenario",
    "SpringerBookScenario",
    # Funder fixture data
    "AUTHORS",
    "DOI_WITH_FUNDERS",
    "FUNDING",
    "JOURNAL_EISSN",
    "JOURNAL_PUBLISHER",
    "JOURNAL_TITLE",
    "LICENSE",
    "PUBLICATION_STATE",
    "TITLE",
    "FundedArticleScenario",
    # Funded article builders
    "configure_funded_article_client",
    "funded_article_metadata",
]
