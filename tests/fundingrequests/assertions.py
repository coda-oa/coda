from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.dto import FundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.dto import PublicationDto


def assert_correct_funding_request(
    author: AuthorDto, publication: PublicationDto, funding: FundingDto
) -> FundingRequest:
    funding_request = FundingRequest.objects.first()
    assert funding_request is not None

    assert_author_equal(author, funding_request)
    assert_publication_equal(publication, funding_request)
    assert_funding_details_equal(funding, funding_request)
    assert funding_request.processing_status == "in_progress"
    return funding_request


def assert_funding_details_equal(funding: FundingDto, funding_request: FundingRequest) -> None:
    assert funding_request.estimated_cost == funding["estimated_cost"]
    assert funding_request.estimated_cost_currency == funding["estimated_cost_currency"]


def assert_publication_equal(publication: PublicationDto, funding_request: FundingRequest) -> None:
    assert funding_request.publication.title == publication["title"]
    assert funding_request.publication.journal.pk == publication["journal"]
    assert len(funding_request.publication.links.all()) == len(publication["links"])
    assert all(
        funding_request.publication.links.filter(
            type=link["link_type"], value=link["link_value"]
        ).exists()
        for link in publication["links"]
    )


def assert_author_equal(author: AuthorDto, funding_request: FundingRequest) -> None:
    assert funding_request.submitter is not None
    assert funding_request.submitter.name == author["name"]
    assert funding_request.submitter.email == author["email"]

    identifier = funding_request.submitter.identifier
    assert identifier is not None
    assert identifier.orcid == author["orcid"]
