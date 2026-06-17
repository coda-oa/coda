from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypedDict, cast

from django.db import models, transaction

from coda.apps.authors import services as author_services
from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.publications.mappers import PublicationDomainMapper
from coda.apps.publications.models import AttachedContract, LinkType, PublicationAttachedConcept
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import Publication as PublicationModel
from coda.domain.author import Author, AuthorNames
from coda.domain.contract import ContractId, ContractYear
from coda.domain.fundingrequest.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.publication import (
    Authors,
    BasePublication,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
)
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import (
    VocabularyConcept,
    VocabularyId,
)


@transaction.atomic
def create(publication: BasePublication) -> PublicationId:
    if publication.id:
        raise PublicationAlreadyCreated(publication.id)

    return _save(publication)


@transaction.atomic
def update(publication: BasePublication) -> None:
    if not publication.id:
        raise UnsavedPublication(publication)

    _save(publication)


def _create_concept_from_domain(concept: VocabularyConcept) -> PublicationAttachedConcept:
    """Create a PublicationAttachedConcept from domain vocabulary concept."""
    return PublicationAttachedConcept(
        entity_id=concept.id,
        vocabulary_id=concept.vocabulary,
        name=concept.name,
    )


@transaction.atomic
def create_many(publications: Iterable[BasePublication]) -> list[PublicationId]:
    pubs = tuple(publications)
    for pub in pubs:
        if pub.id:
            raise PublicationAlreadyCreated(pub.id)

    # Pre-create all PublicationAttachedConcept objects in bulk (2 per publication)
    # Create them with the correct values immediately to avoid needing an update step
    concepts_to_create = [
        _create_concept_from_domain(concept)
        for pub in pubs
        for concept in [pub.publication_type, pub.subject_area]
    ]

    created_concepts = PublicationAttachedConcept.objects.bulk_create(concepts_to_create)

    # Assign concepts to publications (2 concepts per publication)
    concept_index = 0

    def to_model(pub: BasePublication) -> PublicationModel:
        nonlocal concept_index
        publication_type_concept = created_concepts[concept_index]
        subject_area_concept = created_concepts[concept_index + 1]
        concept_index += 2

        match pub:
            case Publication():
                model = PublicationModel(
                    title=pub.title,
                    license=pub.license.name,
                    open_access_type=pub.open_access_type.name,
                    author_list=str(pub.other_authors),
                    publication_state=pub.publication_state.name(),
                    article_journal_id=pub.journal,
                    publication_type=publication_type_concept,
                    subject_area=subject_area_concept,
                )
            case Monograph():
                model = PublicationModel(
                    title=pub.title,
                    license=pub.license.name,
                    open_access_type=pub.open_access_type.name,
                    author_list=str(pub.other_authors),
                    publication_state=pub.publication_state.name(),
                    monograph_publisher_id=pub.publisher,
                    publication_type=publication_type_concept,
                    subject_area=subject_area_concept,
                )
            case _:
                raise ValueError("Unknown publication type")

        if pub.is_published():
            publication_state = cast(Published, pub.publication_state)
            model.online_publication_date = publication_state.online
            model.print_publication_date = publication_state.print

        return model

    to_create = [to_model(pub) for pub in pubs]
    PublicationModel.objects.bulk_create(to_create)

    # Prepare data for bulk operations
    publication_ids = [PublicationId(m.pk) for m in to_create]
    all_authors = [list(pub.relevant_authors) for pub in pubs]
    all_links = [pub.links for pub in pubs]
    all_contracts = [pub.contracts for pub in pubs]

    # Execute bulk operations (each does 1-10 queries total instead of N queries)
    # Note: Concepts are now created with correct values, no update needed
    _attach_contracts_bulk(to_create, all_contracts)
    _attach_links_bulk(publication_ids, all_links)
    _create_authors_bulk(all_authors, publication_ids)

    return [PublicationId(obj.pk) for obj in to_create]


def _save(publication: BasePublication) -> PublicationId:
    match publication:
        case Publication():
            p = _initial_article(publication)
        case Monograph():
            p = _initial_monograph(publication)
        case _:
            raise ValueError("Unknown publication type")

    p.title = publication.title
    p.license = publication.license.name
    p.open_access_type = publication.open_access_type.name
    p.author_list = str(publication.other_authors)
    p.publication_state = publication.publication_state.name()

    if publication.is_published():
        publication_state = cast(Published, publication.publication_state)
        p.online_publication_date = publication_state.online
        p.print_publication_date = publication_state.print

    _save_model_concept(p.publication_type, publication.publication_type)
    _save_model_concept(p.subject_area, publication.subject_area)

    # Explicitly delete old contracts before attaching new ones
    _delete_unused_attached_contracts(p, publication.contracts)
    _attach_contracts(p, publication.contracts)

    p.relevant_authors.all().delete()
    publication_id = PublicationId(p.pk)
    _attach_authors(publication_id, publication.relevant_authors)

    p.links.all().delete()
    _attach_links(publication_id, publication.links)

    p.save()
    return publication_id


def _save_model_concept(
    model_concept: PublicationAttachedConcept, domain_concept: VocabularyConcept
) -> None:
    model_concept.entity_id = domain_concept.id
    model_concept.vocabulary_id = domain_concept.vocabulary
    model_concept.name = domain_concept.name
    model_concept.save()


def get_by_id(publication_id: PublicationId) -> BasePublication:
    return PublicationDomainMapper.map(
        PublicationDomainMapper.prefetch(PublicationModel.objects.all()).get(pk=publication_id)
    )


def get_by_fundingrequest_id(fundingrequest_id: FundingRequestId) -> BasePublication:
    return PublicationDomainMapper.map(
        PublicationDomainMapper.prefetch(PublicationModel.objects.all()).get(
            fundingrequest=fundingrequest_id
        )
    )


def all() -> Sequence[BasePublication]:
    return DomainQuerySet(PublicationModel.objects.all(), PublicationDomainMapper.map)


def first() -> BasePublication | None:
    p = PublicationDomainMapper.prefetch(PublicationModel.objects.all()).first()
    if not p:
        return None

    return PublicationDomainMapper.map(p)


def find_by_doi(doi: Doi) -> BasePublication | None:
    """Find publication by DOI.

    Args:
        doi: DOI to search for

    Returns:
        Publication if found, None otherwise
    """
    model = (
        PublicationDomainMapper.prefetch(PublicationModel.objects.all())
        .filter(links__type__name="DOI", links__value=doi.value())
        .distinct()
        .first()
    )

    if not model:
        return None

    return PublicationDomainMapper.map(model)


def find_publications_by_vocabulary(vocabulary_id: VocabularyId) -> list[BasePublication]:
    query = models.Q(publication_type__vocabulary_id=vocabulary_id) | models.Q(
        subject_area__vocabulary_id=vocabulary_id
    )
    return [PublicationDomainMapper.map(p) for p in PublicationModel.objects.filter(query)]


def get_contracts_for_publication(publication_id: PublicationId) -> Sequence[ContractYear]:
    contracts = AttachedContract.objects.filter(publication_id=publication_id).select_related(
        "contract"
    )
    return DomainQuerySet(contracts, _map_to_contract_year)  # type: ignore[type-var]


def get_contracts_for_publications(
    publication_ids: list[PublicationId],
) -> dict[PublicationId, list[ContractYear]]:
    """Bulk fetch contracts for multiple publications.

    Uses select_related to fetch contract details in single query.
    """
    attached_contracts = (
        AttachedContract.objects.filter(publication_id__in=publication_ids)
        .select_related("contract")
        .order_by("id")
    )

    result: dict[PublicationId, list[ContractYear]] = {}
    for ac in attached_contracts:
        pub_id = PublicationId(ac.publication_id)

        contract = ContractDomainMapper.map(ac.contract)
        contract_year = ContractYear(ac.contract_year, contract)
        result.setdefault(pub_id, []).append(contract_year)

    return result


@dataclass
class FundingRequestReference:
    request_id: str
    url: str


@dataclass(frozen=True)
class PublicationReference:
    id: PublicationId
    title: str
    fundingrequest_reference: FundingRequestReference | None


def get_publication_reference(publication_id: PublicationId) -> PublicationReference | None:
    ref = PublicationModel.objects.filter(pk=publication_id).first()
    if not ref:
        return None

    request_ref = None
    if related_request := getattr(ref, "fundingrequest", None):
        request_id = PublicFundingRequestId.from_str(related_request.request_id)
        request_ref = FundingRequestReference(
            request_id=str(request_id), url=related_request.get_absolute_url()
        )

    return PublicationReference(PublicationId(ref.pk), ref.title, request_ref)


def _map_to_contract_year(c: AttachedContract) -> ContractYear:
    contract = ContractDomainMapper.map(c.contract)
    return ContractYear(c.contract_year, contract)


def _initial_article(publication: Publication) -> PublicationModel:
    if publication.id:
        p = PublicationDomainMapper.prefetch(PublicationModel.objects.all()).get(pk=publication.id)
        p.article_journal_id = publication.journal
    else:
        p = PublicationModel.objects.create(article_journal_id=publication.journal)
    return p


def _initial_monograph(publication: Monograph) -> PublicationModel:
    if publication.id:
        p = PublicationDomainMapper.prefetch(PublicationModel.objects.all()).get(pk=publication.id)
        p.monograph_publisher_id = publication.publisher
    else:
        p = PublicationModel.objects.create(monograph_publisher_id=publication.publisher)
    return p


def _attach_links(id: PublicationId, links: Iterable[Link]) -> None:
    """Attach links to a single publication (used in update operations)."""
    links_list = list(links)
    if not links_list:
        return

    # Fetch all link types in one query
    link_type_names = {link.type() for link in links_list}
    link_types = {lt.name: lt for lt in LinkType.objects.filter(name__in=link_type_names)}

    # Build and bulk create
    link_models = [
        LinkModel(
            value=link.value(),
            type=link_types[link.type()],
            publication_id=cast(int, id),
        )
        for link in links_list
    ]

    LinkModel.objects.bulk_create(link_models)


def _create_link_model(
    pub_id: PublicationId, link: Link, link_types: dict[str, LinkType]
) -> LinkModel | None:
    """Create link model if link type exists."""
    link_type = link_types.get(link.type())
    if not link_type:
        return None

    return LinkModel(
        value=link.value(),
        type=link_type,
        publication_id=cast(int, pub_id),
    )


def _attach_links_bulk(
    publication_ids: Sequence[PublicationId], publications_links: Sequence[Iterable[Link]]
) -> None:
    """Bulk attach links for multiple publications."""
    # Collect all unique link type names
    all_link_type_names = {link.type() for links in publications_links for link in links}

    # Single query to fetch all link types
    if not all_link_type_names:
        return

    link_types = {lt.name: lt for lt in LinkType.objects.filter(name__in=all_link_type_names)}

    # First comprehension: create all potential link models (includes None values)
    potential_links = [
        _create_link_model(pub_id, link, link_types)
        for pub_id, links in zip(publication_ids, publications_links)
        for link in links
    ]

    # Second comprehension: filter out None values
    link_models = [link for link in potential_links if link is not None]

    # Single bulk create
    if link_models:
        LinkModel.objects.bulk_create(link_models)


def _attach_authors(id: PublicationId, relevant_authors: Iterable[Author]) -> None:
    author_services.create_many(list(relevant_authors), id)
    # for author in relevant_authors:
    #     author_id = author_services.author_create(author, id)
    #     author.id = AuthorId(author_id)
    #


def _create_authors_bulk(
    all_authors: Sequence[Sequence[Author]], publication_ids: Sequence[PublicationId]
) -> None:
    """Create ALL authors for ALL publications in a single bulk operation.

    Flattens authors from all publications and creates them in one batch,
    with each author assigned to its correct publication_id.
    """
    flattened_authors_with_pubs: list[tuple[Author, PublicationId]] = [
        (author, pub_id)
        for authors, pub_id in zip(all_authors, publication_ids)
        for author in authors
    ]

    if not flattened_authors_with_pubs:
        return

    author_services.create_many_with_publications(flattened_authors_with_pubs)


def _attach_contracts(p: PublicationModel, contracts: Iterable[ContractYear]) -> None:
    """Attach contracts to a publication.

    Note: This function only creates attachments. It does NOT delete old contracts.
    If you need to clean up old contracts first, call _delete_unused_attached_contracts().
    """
    contract_ids = {cy.contract.id for cy in contracts if cy.contract.id}
    model_contracts = Contract.objects.filter(id__in=contract_ids).order_by("id")

    sorted_contracts = sorted(contracts, key=lambda c: cast(ContractId, c.contract.id))
    model_contract_dict = {c.pk: c for c in model_contracts}

    for contract_year in sorted_contracts:
        cid = cast(ContractId, contract_year.contract.id)
        model_contract = model_contract_dict[cid]
        AttachedContract.objects.get_or_create(
            publication_id=p.pk,
            contract_id=model_contract.pk,
            contract_year=contract_year.year,
        )


def _delete_unused_attached_contracts(
    p: PublicationModel, contracts: Iterable[ContractYear]
) -> None:
    """Delete contracts not in the provided list of contracts."""
    existing_pairs = {(c.contract.id, c.year) for c in contracts}

    # Build list of Q objects for each (contract_id, year) pair
    queries = [
        models.Q(contract_id=contract_id, contract_year=year)
        for contract_id, year in existing_pairs
    ]

    # Combine queries with OR
    combined_query = models.Q()
    for q in queries:
        combined_query |= q

    AttachedContract.objects.filter(publication_id=p.pk).exclude(combined_query).delete()


def _build_contract_attachment(
    pub_pk: int,
    cy: ContractYear,
    existing: set[tuple[int, int, int]],
    model_contracts: dict[int, Contract],
) -> AttachedContract | None:
    """Build contract attachment if not already existing and valid."""
    if not cy.contract.id:
        return None

    key = (pub_pk, cy.contract.id, cy.year)
    if key in existing:
        return None

    model_contract = model_contracts.get(cy.contract.id)
    if not model_contract:
        return None

    return AttachedContract(
        publication_id=pub_pk,
        contract_id=model_contract.pk,
        contract_year=cy.year,
    )


def _attach_contracts_bulk(
    pub_models: Sequence[PublicationModel], contracts_list: Sequence[Iterable[ContractYear]]
) -> None:
    """Bulk attach contracts for multiple publications.

    Note: This function only creates attachments. It does NOT delete old contracts.
    If you need to clean up old contracts first, call _delete_unused_contracts_bulk().
    """
    # Collect all contract IDs
    all_contract_ids = {
        cy.contract.id for contracts in contracts_list for cy in contracts if cy.contract.id
    }

    if not all_contract_ids:
        return

    # Single query to fetch all contracts
    model_contracts = {c.pk: c for c in Contract.objects.filter(id__in=all_contract_ids)}

    # Fetch existing attachments to avoid duplicates
    pub_ids = [p.pk for p in pub_models]
    existing = set(
        AttachedContract.objects.filter(publication_id__in=pub_ids).values_list(
            "publication_id", "contract_id", "contract_year"
        )
    )

    # First comprehension: create all potential attachments (includes None values)
    potential_attachments = [
        _build_contract_attachment(pub.pk, cy, existing, model_contracts)
        for pub, contracts in zip(pub_models, contracts_list)
        for cy in contracts
    ]

    # Second comprehension: filter out None values
    to_create = [attachment for attachment in potential_attachments if attachment is not None]

    if to_create:
        AttachedContract.objects.bulk_create(to_create, ignore_conflicts=True)


class PublicationAlreadyCreated(ValueError):
    def __init__(self, publication_id: PublicationId) -> None:
        super().__init__(f"Publication with ID {publication_id} already exists.")
        self.publication_id = publication_id


class UnsavedPublication(ValueError):
    def __init__(self, publication: BasePublication) -> None:
        super().__init__(f"Publication {publication.title} is not saved and has no id.")
        self.publication = publication


class _CommonPublicationArgs(TypedDict):
    id: PublicationId
    title: NonEmptyStr
    license: License
    relevant_authors: Authors
    other_authors: AuthorNames
    subject_area: VocabularyConcept
    publication_type: VocabularyConcept
    open_access_type: OpenAccessType
    publication_state: PublicationState
    contracts: tuple[ContractYear, ...]
    links: set[Link]
