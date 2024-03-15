from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.dto import PublicationDto


def assert_correct_funding_request(
    author_dto: AuthorDto, publication_dto: PublicationDto, funding_dto: FundingDto
) -> FundingRequest:
    funding_request = FundingRequest.objects.first()
    assert funding_request is not None

    assert_author_equal(author_dto, funding_request.submitter)
    assert_publication_equal(publication_dto, author_dto, funding_request)
    assert_funding_details_equal(funding_dto, funding_request)
    assert funding_request.processing_status == "in_progress"
    return funding_request


def assert_funding_details_equal(funding: FundingDto, funding_request: FundingRequest) -> None:
    assert funding_request.estimated_cost == funding["estimated_cost"]
    assert funding_request.estimated_cost_currency == funding["estimated_cost_currency"]


def assert_publication_equal(
    publication_dto: PublicationDto, author_dto: AuthorDto, funding_request: FundingRequest
) -> None:
    assert funding_request.publication.title == publication_dto["title"]
    assert funding_request.publication.journal.pk == publication_dto["journal"]
    assert len(funding_request.publication.links.all()) == len(publication_dto["links"])
    assert all(
        funding_request.publication.links.filter(
            type=link["link_type"], value=link["link_value"]
        ).exists()
        for link in publication_dto["links"]
    )
    assert_author_equal(author_dto, funding_request.publication.submitting_author)


def assert_author_equal(author_dto: AuthorDto, author: Author | None) -> None:
    assert author is not None
    assert author.name == author_dto["name"]
    assert author.email == author_dto["email"]

    identifier = author.identifier
    assert identifier is not None
    assert identifier.orcid == author_dto["orcid"]

    assert {r.name for r in author.get_roles()} == set(author_dto["roles"] or [])
