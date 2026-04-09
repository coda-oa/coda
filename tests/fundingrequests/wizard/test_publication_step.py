from collections.abc import Iterable
from itertools import zip_longest
from typing import Any, cast

import pytest
from django import forms
from django.http import HttpRequest
from django.test import RequestFactory
from django.utils import timezone

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorFormset
from coda.apps.fundingrequests.views.wizard.steps.publication_step import PublicationStep
from coda.apps.institutions.models import Institution
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import LinkDto, MonographDto, PublicationDto
from coda.apps.publications.forms import PublicationForm
from coda.apps.publications.repositories import vocabulary_repository
from coda.contexts.fundingrequest.services.allowed_vocabularies import AllowedConcepts
from coda.domain.author import Author, AuthorNames, InstitutionId, Role
from coda.domain.publication import Authors
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import Vocabulary, VocabularyConcept, VocabularyProtocol
from tests import domainfactory, modelfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.wizard.stepdata import publication_step
from tests.test_wizard import DictStore

request_factory = RequestFactory()


expected_authors = ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]
author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""


def assert_expected_authors(ctx: dict[str, list[str]]) -> None:
    assert list(ctx["authors"]) == ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]


@pytest.mark.django_db
def test__publication_step__corresponding_author_without_email__is_invalid() -> None:
    create_vocabularies()
    sut = PublicationStep.for_article()
    store = DictStore()

    publication = domainfactory.publication(
        publication_type=an_article_type(), subject_area=a_subject_area()
    )
    publication.relevant_authors = Authors(
        [Author.new(NonEmptyStr("John Doe"), "j.doe@example.com", role=Role.CORRESPONDING_AUTHOR)]
    )
    publication_dto = PublicationDto.from_publication(publication)
    publication_dto.relevant_authors[0].email = ""

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert sut.is_valid(request, store) is False


@pytest.mark.django_db
def test__publication_step_for_article__with_valid_data__is_valid() -> None:
    create_vocabularies()
    sut = PublicationStep.for_article()
    store = DictStore()

    publication = domainfactory.publication(
        publication_type=an_article_type(), subject_area=a_subject_area()
    )
    publication_dto = PublicationDto.from_publication(publication)

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert sut.is_valid(request, store)


@pytest.mark.django_db
def test__publication_step_for_monograph__with_valid_data__is_valid() -> None:
    create_vocabularies()
    sut = PublicationStep.for_monograph()
    store = DictStore()

    publication = domainfactory.monograph(
        publication_type=a_monograph_type(), subject_area=a_subject_area()
    )
    publication_dto = MonographDto.from_monograph(publication)

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert sut.is_valid(request, store)


@pytest.mark.django_db
def test__publication_step__two_relevant_authors_are_submitters__is_invalid() -> None:
    sut = PublicationStep()
    store = DictStore()

    publication_dto = PublicationDto.from_publication(domainfactory.publication())
    publication_dto.relevant_authors = [
        AuthorDto.from_author(domainfactory.author(role=Role.SUBMITTER)),
        AuthorDto.from_author(domainfactory.author(role=Role.SUBMITTING_CORRESPONDING_AUTHOR)),
    ]

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert not sut.is_valid(request, store)


@pytest.mark.django_db
def test__publication_step__done__saves_page_data_to_store() -> None:
    sut = PublicationStep()
    store = DictStore()

    publication = domainfactory.publication()
    publication_dto = PublicationDto.from_publication(publication)

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)
    sut.done(request, store)

    actual = store["publication_step"]
    non_publication_step_items = {"journal", "contracts", "publication_kind"}

    expected_dto = publication_dto.model_copy(deep=True)
    expected = expected_dto.to_post_data(exclude=non_publication_step_items)
    assert actual == expected


@pytest.mark.django_db
def test__publication_step__authors_in_store__get_context_data__contains_authors() -> None:
    sut = PublicationStep()
    store = DictStore()
    publication = domainfactory.publication()
    publication.other_authors = AuthorNames(expected_authors)
    store_data = PublicationDto.from_publication(publication)
    store["publication_step"] = store_data.to_post_data(exclude={"journal", "contracts"})
    store.save()

    ctx = sut.get_context_data(request_factory.get("/"), store)

    assert list(ctx["authors"]) == expected_authors


@pytest.mark.django_db
def test__publication_step__authors_in_post_and_store__get_context_data__prefers_post_data() -> (
    None
):
    sut = PublicationStep()
    store = DictStore()
    publication = domainfactory.publication()
    publication.other_authors = AuthorNames(["John Doe", "Jane Doe"])
    store_data = PublicationDto.from_publication(publication)
    store["publication_step"] = store_data.to_post_data(exclude={"journal", "contracts"})

    step_data = publication_step.stepdata()
    step_data["authors"] = author_str
    request = request_factory.post("/", step_data)
    ctx = sut.get_context_data(request, store)

    assert list(ctx["authors"]) == expected_authors


@pytest.mark.django_db
def test__publication_step__existing_publication__publication_form_uses_allowed_vocabularies() -> (
    None
):
    publication_type_voc = vocabulary_repository.create("publication_type", "1.0")
    publication_type_voc.add_concept("pub-type-1", "Pub Type 1")
    vocabulary_repository.save(publication_type_voc)
    GlobalPreferences.set_article_publication_type_vocabulary(publication_type_voc)

    subject_area_voc = vocabulary_repository.create("subject_area", "1.0")
    subject_area_voc.add_concept("subject-area-1", "Subject Area 1")
    vocabulary_repository.save(subject_area_voc)
    GlobalPreferences.set_subject_classification_vocabulary(subject_area_voc)

    publication = domainfactory.publication(
        subject_area=subject_area_voc.get_concept("subject-area-1"),
        publication_type=publication_type_voc.get_concept("pub-type-1"),
    )
    dto = PublicationDto.from_publication(publication)

    store = DictStore()
    store["publication_step"] = dto.to_post_data(exclude={"journal", "contracts"})
    store.save()

    sut = PublicationStep.for_article()
    ctx = sut.get_context_data(request_factory.get("/"), store)

    pub_form = cast(PublicationForm, ctx["publication_form"])

    assert_has_concept_choices(pub_form, "subject_area", subject_area_voc)
    assert_has_concept_choices(pub_form, "publication_type", publication_type_voc)


@pytest.mark.django_db
def test__publication_step__relevant_authors_in_store__get_context_data__contains_authors() -> None:
    sut = PublicationStep()
    store = DictStore()
    publication = domainfactory.publication()
    publication.relevant_authors = Authors([domainfactory.author()])
    store_data = PublicationDto.from_publication(publication)
    store["publication_step"] = store_data.to_post_data(exclude={"journal", "contracts"})
    store.save()

    ctx = sut.get_context_data(request_factory.get("/"), store)

    author_formset: AuthorFormset = ctx["author_formset"]
    authors = map(AuthorDto.to_author, author_formset.to_dtos())
    for actual, expected in zip_longest(authors, publication.relevant_authors):
        assert_author_eq(actual, expected)


@pytest.mark.django_db
def test__publication_step__relevant_authors_in_store__new_authors_in_request__prefers_new_author() -> (
    None
):
    publication = domainfactory.publication()
    stored_dto = PublicationDto.from_publication(publication)

    new_dto = stored_dto.model_copy()
    expected_author = domainfactory.author()
    new_dto.relevant_authors = [AuthorDto.from_author(expected_author)]

    store = DictStore()
    store["publication_step"] = stored_dto.to_post_data(exclude={"journal", "contracts"})
    store.save()

    request = request_factory.post("/", publication_step.stepdata(new_dto))

    sut = PublicationStep()
    ctx = sut.get_context_data(request, store)

    author_form: AuthorFormset = ctx["author_formset"]
    author_dtos = author_form.to_dtos()
    actual_author = author_dtos[0].to_author()
    assert_author_eq(actual_author, expected_author)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "step_request",
    [
        request_factory.get("/"),
        request_factory.post("/", publication_step.stepdata()),
    ],
)
def test__publication_step_for_article__has_concepts_of_article_publication_type_vocabulary_from_settings(
    step_request: HttpRequest,
) -> None:
    publication_type_voc = vocabulary_repository.create("publication_type", "1.0")
    publication_type_voc.add_concept("pub-type-1", "Pub Type 1")
    vocabulary_repository.save(publication_type_voc)
    GlobalPreferences.set_article_publication_type_vocabulary(publication_type_voc)

    sut = PublicationStep.for_article()
    ctx = sut.get_context_data(step_request, DictStore())

    pub_form = cast(PublicationForm, ctx["publication_form"])
    assert_has_concept_choices(pub_form, "publication_type", publication_type_voc)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "step_request",
    [
        request_factory.get("/"),
        request_factory.post("/", publication_step.stepdata()),
    ],
)
def test__publication_step_for_monograph__has_concepts_of_monograph_publication_type_vocabulary_from_settings(
    step_request: HttpRequest,
) -> None:
    publication_type_voc = vocabulary_repository.create("publication_type", "1.0")
    publication_type_voc.add_concept("pub-type-1", "Pub Type 1")
    vocabulary_repository.save(publication_type_voc)
    GlobalPreferences.set_monograph_publication_type_vocabulary(publication_type_voc)

    sut = PublicationStep.for_monograph()
    ctx = sut.get_context_data(step_request, DictStore())

    pub_form = cast(PublicationForm, ctx["publication_form"])
    assert_has_concept_choices(pub_form, "publication_type", publication_type_voc)


@pytest.mark.django_db
@pytest.mark.parametrize("invalid_link", [("DOI", "10/3939"), ("ISBN", "999-16-148410-0")])
def test__publication_step__invalid_links__is_invalid(invalid_link: tuple[str, str]) -> None:
    link_type, link_value = invalid_link

    sut = PublicationStep()
    store = DictStore()

    publication = domainfactory.publication()
    publication_dto = PublicationDto.from_publication(publication)
    publication_dto.links = [LinkDto(link_type=link_type, link_value=link_value)]

    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert not sut.is_valid(request, store)


@pytest.mark.django_db
def test__existing_author_with_disabled_affiliation_in_store__using_disabled_affiliation_is_valid() -> (
    None
):
    affiliation = modelfactory.institution(enabled=False)
    publication = domainfactory.publication()
    publication.relevant_authors = Authors(
        [domainfactory.author(affiliation=InstitutionId(affiliation.pk))]
    )
    publication_dto = PublicationDto.from_publication(publication)

    store = DictStore()
    store["publication_step"] = publication_dto.to_post_data()
    store.save()

    sut = PublicationStep()
    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert sut.is_valid(request, store)


@pytest.mark.django_db
def test__existing_author_with_archived_affiliation_in_store__using_archived_affiliation_is_valid() -> (
    None
):
    affiliation = Institution.objects.create(name="Archived University")
    affiliation.archived_at = timezone.now()
    affiliation.save()

    publication = domainfactory.publication()
    publication.relevant_authors = Authors(
        [domainfactory.author(affiliation=InstitutionId(affiliation.pk))]
    )
    publication_dto = PublicationDto.from_publication(publication)

    store = DictStore()
    store["publication_step"] = publication_dto.to_post_data()
    store.save()

    sut = PublicationStep()
    stepdata = publication_step.stepdata(publication_dto)
    request = request_factory.post("/", stepdata)

    assert sut.is_valid(request, store)


def create_vocabularies() -> None:
    article_vocabulary()
    monograph_vocabulary()
    subject_areas()


def article_vocabulary() -> Vocabulary:
    v = vocabulary_repository.create("article types", "1.0")
    v.add_concept("article", "Article")
    vocabulary_repository.save(v)
    GlobalPreferences.set_article_publication_type_vocabulary(v)

    return v


def monograph_vocabulary() -> Vocabulary:
    v = vocabulary_repository.create("monograph types", "1.0")
    v.add_concept("monograph", "Monograph")
    vocabulary_repository.save(v)
    GlobalPreferences.set_monograph_publication_type_vocabulary(v)

    return v


def subject_areas() -> Vocabulary:
    v = vocabulary_repository.create("subject_area", "1.0")
    v.add_concept("subject-area-1", "Subject Area 1")
    vocabulary_repository.save(v)

    GlobalPreferences.set_subject_classification_vocabulary(v)
    return v


def an_article_type() -> VocabularyConcept:
    v = GlobalPreferences.get_article_publication_type_vocabulary()
    return next(iter(v.concepts))


def a_subject_area() -> VocabularyConcept:
    v = GlobalPreferences.get_subject_classification_vocabulary()
    return next(iter(v.concepts))


def a_monograph_type() -> VocabularyConcept:
    v = GlobalPreferences.get_monograph_publication_type_vocabulary()
    return next(iter(v.concepts))


def assert_has_concept_choices(
    form: PublicationForm, field_name: str, vocabulary: VocabularyProtocol
) -> None:
    field = cast(forms.ChoiceField, form.fields[field_name])
    choice_names = [name for _, name in cast(Iterable[tuple[Any, str]], field.choices)]
    concept_names = [c.name for c in vocabulary.concepts]
    for concept_name in concept_names:
        assert concept_name in choice_names


@pytest.mark.django_db
def test__with_article_vocabulary__shows_allowed_article_publication_types() -> None:
    v = article_vocabulary()

    form = PublicationForm(concepts=AllowedConcepts.for_new_publication("article"))

    assert_has_concept_choices(form, "publication_type", v)


@pytest.mark.django_db
def test__with_monograph_vocabulary__shows_allowed_monograph_publication_types() -> None:
    v = monograph_vocabulary()

    form = PublicationForm(concepts=AllowedConcepts.for_new_publication("monograph"))

    assert_has_concept_choices(form, "publication_type", v)


@pytest.mark.django_db
def test__with_article_vocabulary__shows_allowed_subject_areas() -> None:
    v = subject_areas()

    form = PublicationForm(concepts=AllowedConcepts.for_new_publication("monograph"))

    assert_has_concept_choices(form, "subject_area", v)


@pytest.mark.django_db
def test__from_dto__article_kind__shows_allowed_article_publication_types() -> None:
    create_vocabularies()
    publication = domainfactory.publication(
        publication_type=an_article_type(), subject_area=a_subject_area()
    )
    dto = PublicationDto.from_publication(publication).meta

    form = PublicationForm.from_dto(dto, AllowedConcepts.for_existing_publication(publication))

    assert_has_concept_choices(
        form, "publication_type", GlobalPreferences.get_article_publication_type_vocabulary()
    )


@pytest.mark.django_db
def test__from_dto__monograph_kind__shows_allowed_monograph_publication_types() -> None:
    create_vocabularies()
    publication = domainfactory.monograph(
        publication_type=a_monograph_type(), subject_area=a_subject_area()
    )
    dto = MonographDto.from_monograph(publication).meta

    form = PublicationForm.from_dto(dto, AllowedConcepts.for_existing_publication(publication))

    assert_has_concept_choices(
        form, "publication_type", GlobalPreferences.get_monograph_publication_type_vocabulary()
    )


@pytest.mark.django_db
def test__from_dto__article_kind__grandfathers_existing_pub_type_removed_from_vocabulary() -> None:
    """A concept that was removed from the allowed vocabulary is still selectable (grandfather clause)."""
    create_vocabularies()

    # A concept NOT in the article vocabulary
    other_vocab = vocabulary_repository.create("other", "1.0")
    other_vocab.add_concept("legacy-type", "Legacy Type")
    vocabulary_repository.save(other_vocab)
    legacy_concept = other_vocab.get_concept("legacy-type")

    publication = domainfactory.publication(
        publication_type=legacy_concept, subject_area=a_subject_area()
    )
    dto = PublicationDto.from_publication(publication).meta

    form = PublicationForm.from_dto(dto, AllowedConcepts.for_existing_publication(publication))

    field = cast(forms.ChoiceField, form.fields["publication_type"])
    choice_names = [name for _, name in cast(Iterable[tuple[Any, str]], field.choices)]
    assert "Legacy Type" in choice_names


@pytest.mark.django_db
def test__publication_step_for_article__restores_from_store_with_article_vocabulary() -> None:
    """When restoring from the store, for_article() uses article vocabulary."""
    create_vocabularies()
    publication = domainfactory.publication(
        publication_type=an_article_type(), subject_area=a_subject_area()
    )
    dto = PublicationDto.from_publication(publication)

    store = DictStore()
    store["publication_step"] = dto.to_post_data(exclude={"journal", "contracts"})
    store.save()

    sut = PublicationStep.for_article()
    ctx = sut.get_context_data(request_factory.get("/"), store)

    pub_form = cast(PublicationForm, ctx["publication_form"])
    assert_has_concept_choices(
        pub_form, "publication_type", GlobalPreferences.get_article_publication_type_vocabulary()
    )


@pytest.mark.django_db
def test__publication_step_for_monograph__restores_from_store_with_monograph_vocabulary() -> None:
    """When restoring from the store, for_monograph() uses monograph vocabulary."""
    create_vocabularies()
    publication = domainfactory.monograph(
        publication_type=a_monograph_type(), subject_area=a_subject_area()
    )
    dto = MonographDto.from_monograph(publication)

    store = DictStore()
    store["publication_step"] = dto.to_post_data(exclude={"publisher", "contracts"})
    store.save()

    sut = PublicationStep.for_monograph()
    ctx = sut.get_context_data(request_factory.get("/"), store)

    pub_form = cast(PublicationForm, ctx["publication_form"])
    assert_has_concept_choices(
        pub_form, "publication_type", GlobalPreferences.get_monograph_publication_type_vocabulary()
    )


# --- Fix M1: mutable default argument in PublicationForm.__init__ ---


def test__publication_form__no_args__constructs_without_error() -> None:
    """PublicationForm() with no arguments must construct successfully."""
    PublicationForm()


def test__publication_form__no_args__has_empty_concept_choices() -> None:
    """PublicationForm() with no arguments must have only the empty sentinel choice for concepts."""
    from coda.apps.publications.forms._fields import EMPTY_CHOICE

    form = PublicationForm()
    subject_area_choices = list(
        cast(
            Iterable[tuple[Any, str]], cast(forms.ChoiceField, form.fields["subject_area"]).choices
        )
    )
    publication_type_choices = list(
        cast(
            Iterable[tuple[Any, str]],
            cast(forms.ChoiceField, form.fields["publication_type"]).choices,
        )
    )
    # Only the empty sentinel; no concepts from shared state
    assert subject_area_choices == [
        EMPTY_CHOICE
    ], f"Expected only EMPTY_CHOICE but got: {subject_area_choices}"
    assert publication_type_choices == [
        EMPTY_CHOICE
    ], f"Expected only EMPTY_CHOICE but got: {publication_type_choices}"


def test__publication_form__two_instances_without_args__do_not_share_concept_state() -> None:
    """Two PublicationForm() instances must not share the same _ConceptCollections default object.

    This guards against the mutable-default-argument footgun: if concepts were
    mutated on one instance, the other must not be affected.
    """
    from coda.apps.publications.forms._fields import ConceptChoiceField
    from coda.domain.vocabulary import UnknownConcept

    form_a = PublicationForm()
    form_b = PublicationForm()

    # Mutate the internal concept list on form_a's subject_area field directly.
    # If the two forms share state (the original mutable-default bug), this mutation
    # would also appear in form_b — which must NOT happen.
    subject_area_field_a = cast(ConceptChoiceField, form_a.fields["subject_area"])
    subject_area_field_b = cast(ConceptChoiceField, form_b.fields["subject_area"])

    # Confirm both start empty
    assert list(subject_area_field_a._concepts) == []
    assert list(subject_area_field_b._concepts) == []

    # Mutate form_a's concept collection
    sentinel_concept = UnknownConcept
    subject_area_field_a._concepts = [sentinel_concept]

    # form_b must remain unaffected — this is the key assertion that catches the bug
    assert (
        list(subject_area_field_b._concepts) == []
    ), "form_b's subject_area concepts were affected by mutating form_a — shared state detected!"
