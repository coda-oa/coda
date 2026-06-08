"""Test fixtures for publication context.

Re-exports metadata builders and sample fixtures for clean imports:

    from tests.contexts.publication.fixtures import (
        article_metadata,
        book_metadata,
        nature_article_metadata,
        springer_book_metadata,
        NATURE_EISSN,
        NATURE_JOURNAL_TITLE,
    )
"""

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
    "NATURE_EISSN",
    "NATURE_JOURNAL_TITLE",
    "article_metadata",
    "book_metadata",
    "nature_article_metadata",
    "springer_book_metadata",
]
