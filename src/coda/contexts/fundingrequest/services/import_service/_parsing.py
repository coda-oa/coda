"""Parsing logic for converting import DTOs to domain objects.

Consolidates all DTO parsers into focused functions organized by entity type.
"""

from coda.apps.authors.dto import AuthorDto
from coda.apps.publications.dto import (
    ConceptDto,
    ContractYearDto,
    JournalDto,
    LinkDto,
    MonographDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    CreateReviewDto,
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.dto.import_dtos import (
    AuthorImportDto,
    ConceptImportDto,
    ContractImportDto,
    CostEstimateImportDto,
    FundingRequestImportDto,
    FundingRequestImportListDto,
    PublicationImportDto,
    ResearchFundingImportDto,
    ReviewImportDto,
)
from coda.domain.contract import PublisherId
from coda.domain.vocabulary import UnknownConcept

from .types import ImportLookups


class ConceptValidationErrors(ValueError):
    """Raised when multiple concept validation errors occur during parsing."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Multiple concept validation errors: {len(errors)} error(s)")


def parse_requests(
    import_data: FundingRequestImportListDto,
    lookups: ImportLookups,
    errors: dict[str, list[str]],
) -> list[CreateFundingRequestDto]:
    """Parse all import DTOs to CreateFundingRequestDto."""
    creation_dtos = []
    for request_dto in import_data.requests:
        try:
            creation_dto = _parse_single_request(request_dto, lookups)
            creation_dtos.append(creation_dto)
        except ConceptValidationErrors as e:
            key = request_dto.legacy_request_id or request_dto.publication.title
            errors.setdefault(key, []).extend(e.errors)
        except ValueError as e:
            key = request_dto.legacy_request_id or request_dto.publication.title
            errors.setdefault(key, []).append(str(e))

    return creation_dtos


def _parse_single_request(
    request_dto: FundingRequestImportDto,
    lookups: ImportLookups,
) -> CreateFundingRequestDto:
    """Parse a single funding request DTO."""
    return CreateFundingRequestDto(
        publication=parse_publication(request_dto.publication, lookups),
        payment=parse_cost_estimate(request_dto.estimated_cost),
        extra_information=parse_extra_information(request_dto),
        funding=[parse_funding(f, lookups) for f in request_dto.research_funding],
        request_date=request_dto.request_date,
        legacy_request_id=request_dto.legacy_request_id,
        review=parse_review(request_dto.review),
    )


def parse_publication(
    import_dto: PublicationImportDto,
    lookups: ImportLookups,
) -> PublicationDto | MonographDto:
    """Parse publication DTO (article or monograph)."""
    links = [
        LinkDto(
            link_type=link.type,
            link_value=link.value,
        )
        for link in import_dto.links
    ]

    # Parse concepts with error collection
    concept_errors = []
    publication_type_result = None
    subject_area_result = None

    # Try parsing publication_type
    try:
        publication_type_result = parse_concept(import_dto.publication_type, lookups)
    except ValueError as e:
        concept_errors.append(str(e))

    # Try parsing subject_area
    try:
        subject_area_result = parse_concept(import_dto.subject_area, lookups)
    except ValueError as e:
        concept_errors.append(str(e))

    # If any concept parsing failed, raise combined error
    if concept_errors:
        raise ConceptValidationErrors(concept_errors)

    # Both concepts valid - mypy knows they're non-None here
    assert publication_type_result is not None
    assert subject_area_result is not None

    meta = PublicationMetaDto(
        title=import_dto.title,
        publication_type=publication_type_result,
        subject_area=subject_area_result,
        publication_state=import_dto.publishing_state.state,
        online_publication_date=import_dto.publishing_state.online_date,
        print_publication_date=import_dto.publishing_state.print_date,
        license=import_dto.license.name,
        open_access_type=import_dto.open_access_type.name,
    )

    authors = [parse_author(author_dto, lookups) for author_dto in import_dto.authors]
    contracts = [parse_contract(contract_dto, lookups) for contract_dto in import_dto.contracts]

    if import_dto.kind == "article":
        return PublicationDto(
            meta=meta,
            journal=_parse_journal(import_dto, lookups),
            links=links,
            relevant_authors=authors,
            other_authors=[],
            contracts=contracts,
        )
    elif import_dto.kind == "monograph":
        return MonographDto(
            meta=meta,
            publisher=_parse_publisher(import_dto, lookups),
            links=links,
            relevant_authors=authors,
            other_authors=[],
            contracts=contracts,
        )
    else:
        raise ValueError(f"Unknown publication kind: {import_dto.kind}")


def _parse_journal(import_dto: PublicationImportDto, lookups: ImportLookups) -> JournalDto:
    """Parse journal from publication data using pre-fetched lookup."""
    journal = lookups.journals.get(import_dto.eissn)
    if not journal:
        raise ValueError(f"Journal with EISSN '{import_dto.eissn}' not found in lookups")
    return JournalDto(id=journal.pk)


def _parse_publisher(import_dto: PublicationImportDto, lookups: ImportLookups) -> PublisherId:
    """Parse publisher from publication data using pre-fetched lookup.

    Publisher is guaranteed to exist in lookup because:
    - Monograph publishers are created in _build_publisher_lookup()
    - Article publishers are created in _build_publisher_lookup() OR
      come from existing journals (added to lookup in build_entity_lookups())
    """
    publisher = lookups.publishers[import_dto.publisher_name]
    return PublisherId(publisher.pk)


def parse_author(import_dto: AuthorImportDto, lookups: ImportLookups) -> AuthorDto:
    """Parse author DTO with affiliation lookup."""
    affiliation = _parse_affiliation(import_dto, lookups)
    return AuthorDto(
        name=import_dto.name,
        email=import_dto.email,
        orcid=import_dto.orcid,
        role=import_dto.role.name,
        affiliation=affiliation,
    )


def _parse_affiliation(import_dto: AuthorImportDto, lookups: ImportLookups) -> int | None:
    """Parse affiliation from import DTO using lookups."""
    if import_dto.affiliation is None:
        return None

    institution = lookups.institutions[import_dto.affiliation]
    return institution.pk


def parse_contract(import_dto: ContractImportDto, lookups: ImportLookups) -> ContractYearDto:
    """Parse contract DTO with contract lookup."""
    contract = lookups.contracts[import_dto.name]
    assert contract.id.resolved
    return ContractYearDto(contract=contract.id.pk, year=import_dto.year)


def parse_concept(import_dto: ConceptImportDto, lookups: ImportLookups) -> ConceptDto:
    """Parse vocabulary concept DTO."""
    if not import_dto.name:
        return ConceptDto.from_concept(UnknownConcept)

    vocabulary = lookups.vocabularies.get(import_dto.vocabulary_name)
    if not vocabulary:
        raise ValueError(f"Vocabulary '{import_dto.vocabulary_name}' not found")

    for concept in vocabulary.concepts:
        if concept.name == import_dto.name:
            return ConceptDto.from_concept(concept)

    raise ValueError(
        f"Concept '{import_dto.name}' not found in vocabulary '{import_dto.vocabulary_name}'"
    )


def parse_cost_estimate(import_dto: CostEstimateImportDto) -> PaymentDto:
    """Parse cost estimate to payment DTO."""
    return PaymentDto(
        amount=float(import_dto.amount),
        currency=import_dto.currency,
        method=import_dto.payment_method.value,
    )


def parse_funding(
    import_dto: ResearchFundingImportDto,
    lookups: ImportLookups,
) -> ExternalFundingDto:
    """Parse research funding with organization lookup."""
    return ExternalFundingDto(
        organization=_parse_funder(import_dto, lookups),
        project_id=import_dto.project_id,
        project_name=import_dto.project_name,
    )


def _parse_funder(import_dto: ResearchFundingImportDto, lookups: ImportLookups) -> int:
    """Parse funder organization using lookups."""
    org = lookups.funding_organizations[import_dto.funder]
    return org.pk


def parse_extra_information(import_dto: FundingRequestImportDto) -> ExtraInformationDto:
    """Parse extra information (contact, remarks)."""
    return ExtraInformationDto(
        request_remarks=import_dto.request_remarks,
        extra_contact=ExtraContactDto(
            name=import_dto.seperate_contact.name,
            email=import_dto.seperate_contact.email,
        ),
    )


def parse_review(import_dto: ReviewImportDto) -> CreateReviewDto:
    """Parse review DTO from import data."""
    return CreateReviewDto(
        decided_funding_amount=float(import_dto.funding.amount),
        decided_funding_currency=import_dto.funding.currency,
        reviewer_remarks=import_dto.remarks,
        result=import_dto.result.value,
    )
