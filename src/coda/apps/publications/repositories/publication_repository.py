from collections.abc import Iterable, Sequence
from typing import TypedDict, cast

from django.db import models, transaction

from coda.apps.authors import services as author_services
from coda.apps.contracts import mapper as contract_mapper
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.publications.models import AttachedContract, LinkType, PublicationAttachedConcept
from coda.apps.publications.models import Link as LinkModel
from coda.apps.publications.models import Publication as PublicationModel
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.author import Author, AuthorId, AuthorNames
from coda.domain.contract import ContractId, ContractYear, PublisherId
from coda.domain.publication import (
    Authors,
    BasePublication,
    JournalId,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationId,
    PublicationState,
    Published,
    Unpublished,
    UnpublishedState,
    links,
)
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import ConceptId, UnknownConcept, VocabularyConcept, VocabularyId


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


@transaction.atomic
def create_many(publications: Iterable[BasePublication]) -> list[PublicationId]:
    pubs = tuple(publications)
    for pub in pubs:
        if pub.id:
            raise PublicationAlreadyCreated(pub.id)

    def to_model(pub: BasePublication) -> PublicationModel:
        match pub:
            case Publication():
                model = PublicationModel(
                    title=pub.title,
                    license=pub.license.name,
                    open_access_type=pub.open_access_type.name,
                    author_list=str(pub.other_authors),
                    publication_state=pub.publication_state.name(),
                    article_journal_id=pub.journal,
                )
            case Monograph():
                model = PublicationModel(
                    title=pub.title,
                    license=pub.license.name,
                    open_access_type=pub.open_access_type.name,
                    author_list=str(pub.other_authors),
                    publication_state=pub.publication_state.name(),
                    monograph_publisher_id=pub.publisher,
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

    for model, pub in zip(to_create, pubs):
        _save_model_concept(model.publication_type, pub.publication_type)
        _save_model_concept(model.subject_area, pub.subject_area)
        _attach_contracts(model, pub.contracts)
        _attach_links(PublicationId(model.pk), pub.links)
        author_services.create_many(list(pub.relevant_authors), PublicationId(model.pk))

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
    model = (
        PublicationModel.objects.select_related(
            "article_journal", "monograph_publisher", "publication_type", "subject_area"
        )
        .prefetch_related(
            "relevant_authors__affiliation",
            "relevant_authors__identifier",
            "attached_contracts__contract__publishers",
            "attached_contracts__contract__journals",
            "links__type",
        )
        .get(pk=publication_id)
    )
    return as_domain_object(model)


def all() -> Sequence[BasePublication]:
    return DomainQuerySet(PublicationModel.objects.all(), as_domain_object)


def first() -> BasePublication | None:
    p = PublicationModel.objects.first()
    if not p:
        return None

    return as_domain_object(p)


def find_publications_by_vocabulary(vocabulary_id: VocabularyId) -> list[BasePublication]:
    query = models.Q(publication_type__vocabulary_id=vocabulary_id) | models.Q(
        subject_area__vocabulary_id=vocabulary_id
    )
    return [as_domain_object(p) for p in PublicationModel.objects.filter(query)]


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
    attached_contracts = AttachedContract.objects.filter(
        publication_id__in=publication_ids
    ).select_related("contract")

    result: dict[PublicationId, list[ContractYear]] = {}
    for ac in attached_contracts:
        pub_id = PublicationId(ac.publication_id)

        contract = contract_mapper.as_domain_object(ac.contract)
        contract_year = ContractYear(ac.contract_year, contract)
        result.setdefault(pub_id, []).append(contract_year)

    return result


def _map_to_contract_year(c: AttachedContract) -> ContractYear:
    contract = contract_mapper.as_domain_object(c.contract)
    return ContractYear(c.contract_year, contract)


def as_domain_object(model: PublicationModel) -> BasePublication:
    common_args = _common_args(model)
    if model.article_journal_id:
        return Publication(
            **common_args,
            journal=JournalId(model.article_journal_id),
        )
    elif model.monograph_publisher_id:
        return Monograph(
            **common_args,
            publisher=PublisherId(model.monograph_publisher_id),
        )
    else:
        raise ValueError("Unknown publication type")


def _common_args(model: PublicationModel) -> "_CommonPublicationArgs":
    return _CommonPublicationArgs(
        id=PublicationId(model.pk),
        title=NonEmptyStr(model.title),
        license=License[model.license],
        open_access_type=OpenAccessType[model.open_access_type],
        publication_type=_deserialize_concept(model.publication_type),
        subject_area=_deserialize_concept(model.subject_area),
        relevant_authors=Authors(
            author_services.as_domain_object(a) for a in model.relevant_authors.all()
        ),
        other_authors=AuthorNames.from_str(model.author_list or ""),
        publication_state=_deserialize_publication_state(model),
        contracts=tuple(
            ContractYear(c.contract_year, contract_mapper.as_domain_object(c.contract))
            for c in model.attached_contracts.all()
        ),
        links=_deserialize_links(model.links.all()),
    )


def _initial_article(publication: Publication) -> PublicationModel:
    if publication.id:
        p = PublicationModel.objects.get(pk=publication.id)
        p.article_journal_id = publication.journal
    else:
        p = PublicationModel.objects.create(article_journal_id=publication.journal)

    return p


def _initial_monograph(publication: Monograph) -> PublicationModel:
    if publication.id:
        p = PublicationModel.objects.get(pk=publication.id)
        p.monograph_publisher_id = publication.publisher
    else:
        p = PublicationModel.objects.create(monograph_publisher_id=publication.publisher)

    return p


def _deserialize_publication_state(model: PublicationModel) -> PublicationState:
    state: PublicationState
    if getattr(model, "publication_state") == Published.name():
        state = Published(online=model.online_publication_date, print=model.print_publication_date)
    else:
        state = Unpublished(state=UnpublishedState[model.publication_state])
    return state


def _deserialize_concept(model_concept: PublicationAttachedConcept) -> VocabularyConcept:
    if model_concept.entity_id == UnknownConcept.id:
        return UnknownConcept

    v = vocabulary_repository.get_by_id(cast(VocabularyId, model_concept.vocabulary_id))
    return v.get_concept_by_id(ConceptId(str(model_concept.entity_id)))


def _deserialize_links(links_: Iterable[LinkModel]) -> set[Link]:
    return {links.create_link(link_type=link.type.name, link_value=link.value) for link in links_}


def _attach_links(id: PublicationId, links: Iterable[Link]) -> None:
    for link in links:
        LinkModel.objects.create(
            value=link.value(),
            type=LinkType.objects.get(name=link.type()),
            publication_id=cast(int, id),
        )


def _attach_authors(id: PublicationId, relevant_authors: Iterable[Author]) -> None:
    for author in relevant_authors:
        author_id = author_services.author_create(author, id)
        author.id = AuthorId(author_id)


def _attach_contracts(p: PublicationModel, contracts: Iterable[ContractYear]) -> None:
    contract_ids = {cy.contract.id for cy in contracts if cy.contract.id}
    model_contracts = Contract.objects.filter(id__in=contract_ids).order_by("id")
    _delete_unused_attached_contracts(p, contracts)

    sorted_contracts = sorted(contracts, key=lambda c: cast(ContractId, c.contract.id))
    model_contract_dict = {c.id: c for c in model_contracts}

    for contract_year in sorted_contracts:
        cid = cast(ContractId, contract_year.contract.id)
        model_contract = model_contract_dict[cid]
        AttachedContract.objects.get_or_create(
            publication_id=p.pk, contract_id=model_contract.pk, contract_year=contract_year.year
        )


def _delete_unused_attached_contracts(
    p: PublicationModel, contracts: Iterable[ContractYear]
) -> None:
    existing_pairs = {(c.contract.id, c.year) for c in contracts}
    query = models.Q()
    for contract_id, year in existing_pairs:
        query |= models.Q(contract_id=contract_id) & models.Q(contract_year=year)
    AttachedContract.objects.filter(publication_id=p.id).exclude(query).delete()


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
