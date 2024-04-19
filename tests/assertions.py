from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.models import Author
from coda.apps.fundingrequests.dto import CostDto, ExternalFundingDto
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.publications.dto import PublicationDto
from coda.apps.publications.models import Publication


def assert_correct_funding_request(
    author_dto: AuthorDto,
    publication_dto: PublicationDto,
    external_funding_dto: ExternalFundingDto,
    cost_dto: CostDto,
) -> FundingRequest:
    funding_request = FundingRequest.objects.first()
    assert funding_request is not None

    assert_author_equal(author_dto, funding_request.submitter)
    assert_publication_equal(publication_dto, author_dto, funding_request.publication)
    assert_external_funding_equal(external_funding_dto, funding_request)
    assert_cost_equal(cost_dto, funding_request)
    assert funding_request.processing_status == "in_progress"
    return funding_request


def assert_external_funding_equal(
    external_funding: ExternalFundingDto, funding_request: FundingRequest
) -> None:
    assert funding_request.external_funding is not None
    assert funding_request.external_funding.organization.pk == external_funding["organization"]
    assert funding_request.external_funding.project_id == external_funding["project_id"]
    assert funding_request.external_funding.project_name == external_funding["project_name"]


def assert_cost_equal(funding: CostDto, funding_request: FundingRequest) -> None:
    assert funding_request.payment_method == funding["payment_method"]
    assert funding_request.estimated_cost == funding["estimated_cost"]
    assert funding_request.estimated_cost_currency == funding["estimated_cost_currency"]


def assert_publication_equal(
    publication_dto: PublicationDto, author_dto: AuthorDto, publication: Publication
) -> None:
    assert publication.title == publication_dto["title"]
    assert publication.authors == publication_dto["authors"], author_error_msg(
        publication_dto, publication
    )
    assert publication.open_access_type == publication_dto["open_access_type"]
    assert publication.license == publication_dto["license"]
    assert publication.journal.pk == publication_dto["journal"]
    assert (
        publication.publication_date == publication_dto["publication_date"]
    ), f"{type(publication.publication_date)} != {type(publication_dto['publication_date'])}"
    assert publication.publication_state == publication_dto["publication_state"]
    assert len(publication.links.all()) == len(publication_dto["links"])
    assert all(
        publication.links.filter(type=link["link_type"], value=link["link_value"]).exists()
        for link in publication_dto["links"]
    )
    assert_author_equal(author_dto, publication.submitting_author)


def author_error_msg(publication_dto: PublicationDto, publication: Publication) -> str:
    dto_authors = repr(publication_dto["authors"])
    publication_authors = repr(publication.authors)
    return f"Expected: {dto_authors}, Got: {publication_authors}"


def assert_author_equal(author_dto: AuthorDto, author: Author | None) -> None:
    assert author is not None
    assert author.name == author_dto["name"]
    assert author.email == author_dto["email"]

    identifier = author.identifier
    assert identifier is not None
    assert identifier.orcid == author_dto["orcid"]

    assert {r.name for r in author.get_roles()} == set(author_dto["roles"] or [])
