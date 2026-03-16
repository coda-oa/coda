"""Test metadata fixtures for DOI import tests.

This module contains predefined metadata for common test cases.
Tests can use these to configure the FakeDOIMetadataClient.
"""

import datetime

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)


def nature_article_metadata() -> ExternalPublicationMetadata:
    """Metadata for a sample Nature journal article.

    This represents a typical journal article with:
    - Multiple authors with affiliations
    - Journal with ISSN and E-ISSN
    - CC-BY license
    - Online publication date
    """
    return ExternalPublicationMetadata(
        title="Example Nature Article",
        authors=[
            ExternalAuthor(
                name="John Doe",
                affiliation="University of Example",
                ror_id="https://ror.org/01an7q238",
            ),
            ExternalAuthor(
                name="Jane Smith",
                affiliation="Research Institute",
                ror_id=None,
            ),
        ],
        publication_type="journal-article",
        journal=ExternalJournal(
            title="Nature",
            issn="0028-0836",
            eissn="1476-4687",
        ),
        publisher="Springer Science and Business Media LLC",
        license="CC-BY",
        online_publication_date=datetime.date(2024, 1, 15),
    )


def springer_book_metadata() -> ExternalPublicationMetadata:
    """Metadata for a sample Springer book.

    This represents a typical book/monograph with:
    - Single author
    - ISBN (print)
    - Print publication date
    - No journal (books don't have journals)
    """
    return ExternalPublicationMetadata(
        title="Quantum Microscopy of Biological Systems",
        authors=[
            ExternalAuthor(
                name="Michael Taylor",
                affiliation=None,
                ror_id=None,
            ),
        ],
        publication_type="book",
        journal=None,
        isbn="9783319189376",
        publisher="Springer International Publishing",
        license=None,
        print_publication_date=datetime.date(2015, 1, 1),
    )
