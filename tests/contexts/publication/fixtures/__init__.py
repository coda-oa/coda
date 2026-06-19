"""Test fixtures for publication context.

Re-exports metadata builders, sample fixtures, and funder data for clean imports:

    from tests.contexts.publication.fixtures import (
        article_metadata,
        book_metadata,
        nature_article_metadata,
        springer_book_metadata,
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
)
from tests.contexts.publication.fixtures.metadata import (
    NATURE_EISSN,
    NATURE_JOURNAL_TITLE,
    article_metadata,
    book_metadata,
)
from tests.contexts.publication.fixtures.sample_metadata import (
    nature_article_metadata,
    springer_book_metadata,
)

__all__ = [
    # Builders
    "NATURE_EISSN",
    "NATURE_JOURNAL_TITLE",
    "article_metadata",
    "book_metadata",
    # Samples
    "nature_article_metadata",
    "springer_book_metadata",
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
    # Funded article builders
    "configure_funded_article_client",
    "funded_article_metadata",
]
