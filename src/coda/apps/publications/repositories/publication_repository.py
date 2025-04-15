from collections.abc import Iterable, Sequence
from typing import TypedDict, cast

from django.db import transaction
from django.db.models import Q

from coda.apps.authors import services as author_services
from coda.apps.contracts import repository as contract_services
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
def save(publication: BasePublication) -> PublicationId:
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
    model = PublicationModel.objects.get(pk=publication_id)
    return as_domain_object(model)


def all() -> Sequence[BasePublication]:
    return DomainQuerySet(PublicationModel.objects.all(), as_domain_object)


def first() -> BasePublication | None:
    p = PublicationModel.objects.first()
    if not p:
        return None

    return as_domain_object(p)


def find_publications_by_vocabulary(vocabulary_id: VocabularyId) -> list[BasePublication]:
    query = Q(publication_type__vocabulary_id=vocabulary_id) | Q(
        subject_area__vocabulary_id=vocabulary_id
    )
    return [as_domain_object(p) for p in PublicationModel.objects.filter(query)]


def get_contracts_for_publication(publication_id: PublicationId) -> Sequence[ContractYear]:
    contracts = AttachedContract.objects.filter(publication_id=publication_id)
    return DomainQuerySet(contracts, _map_to_contract_year)  # type: ignore[type-var]


def _map_to_contract_year(c: AttachedContract) -> ContractYear:
    return contract_services.as_domain_object(c.contract).in_year(c.contract_year)


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
            contract_services.as_domain_object(c.contract).in_year(c.contract_year)
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

    _delete_unused_attached_contracts(p, contract_ids)

    sorted_contracts = sorted(contracts, key=lambda c: cast(ContractId, c.contract.id))
    for model_contract, contract_year in zip(model_contracts, sorted_contracts):
        AttachedContract.objects.get_or_create(
            publication_id=p.pk, contract_id=model_contract.pk, contract_year=contract_year.year
        )


def _delete_unused_attached_contracts(p: PublicationModel, contracts: Iterable[ContractId]) -> None:
    AttachedContract.objects.filter(publication_id=p.id).exclude(contract__in=contracts).delete()


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
