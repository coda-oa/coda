from typing import cast

import pytest
from django import forms
from django.http import HttpRequest
from django.test import RequestFactory

from coda.apps.authors.dto import AuthorDto
from coda.apps.authors.forms import AuthorForm
from coda.apps.fundingrequests.views.wizard.wizardsteps import PublicationStep
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.apps.publications.forms import PublicationForm
from coda.apps.publications.repositories import vocabulary_repository
from coda.author import AuthorList, Role
from coda.vocabulary import Vocabulary, VocabularyConcept
from tests import domainfactory
from tests.authors.test__author import assert_author_eq
from tests.fundingrequests.wizard.stepdata import publication_step
from tests.test_wizard import DictStore

request_factory = RequestFactory()


expected_authors = ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]
author_str = """John Doe, Jane Doe, John Smith,
     and Anna Smith"""


def assert_expected_authors(ctx: dict[str, list[str]]) -> None:
    assert list(ctx["authors"]) == ["John Doe", "Jane Doe", "John Smith", "Anna Smith"]


def parse() -> dict[str, str]:
    return {"action": "parse_authors"}


def parse_authors_request(
    author_str: str, publication_data: dict[str, str] | None = None
) -> HttpRequest:
    return request_factory.post(
        "/",
        (publication_data or publication_step.empty_stepdata())
        | {"action": "parse_authors", "authors": author_str},
    )


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
def test__publication_step__action__parse_authors__adds_author_list_to_context() -> None:
    sut = PublicationStep()

    ctx = sut.get_context_data(parse_authors_request(author_str), DictStore())

    assert_expected_authors(ctx)


@pytest.mark.django_db
def test__publication_step__action__parse_authors__does_not_progress() -> None:
    sut = PublicationStep()
    store = DictStore()

    request = parse_authors_request(author_str)
    ctx = sut.get_context_data(request, store)

    assert not sut.is_valid(request, store)
    assert ctx["publication_form"].errors == {}


@pytest.mark.django_db
def test__publication_step__action__parse_authors__retains_posted_data_but_does_not_show_errors() -> (
    None
):
    sut = PublicationStep()
    store = DictStore()

    incomplete_publication_data = publication_step.stepdata()
    incomplete_publication_data.pop("license")

    request = parse_authors_request(author_str, incomplete_publication_data)
    ctx = sut.get_context_data(request, store)

    form = ctx["publication_form"]
    assert form.data != {}
    assert form.errors == {}


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
    non_publication_step_items = {"journal", "contracts"}

    expected_dto = publication_dto.model_copy(deep=True)
    expected = expected_dto.to_post_data(exclude=non_publication_step_items)
    assert actual == expected


@pytest.mark.django_db
def test__publication_step__authors_in_store__get_context_data__contains_authors() -> None:
    sut = PublicationStep()
    store = DictStore()
    publication = domainfactory.publication()
    publication.authors = AuthorList(expected_authors)
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
    publication.authors = AuthorList(["John Doe", "Jane Doe"])
    store_data = PublicationDto.from_publication(publication)
    store["publication_step"] = store_data.to_post_data(exclude={"journal", "contracts"})

    step_data = publication_step.stepdata()
    step_data["authors"] = author_str
    request = request_factory.post("/", step_data)
    ctx = sut.get_context_data(request, store)

    assert list(ctx["authors"]) == expected_authors


@pytest.mark.django_db
def test__publication_step__existing_publication__publication_form_uses_existing_vocabularies() -> (
    None
):
    publication_type_voc = vocabulary_repository.create("publication_type", "1.0")
    publication_type_voc.add_concept("pub-type-1", "Pub Type 1")
    vocabulary_repository.save(publication_type_voc)

    subject_area_voc = vocabulary_repository.create("subject_area", "1.0")
    subject_area_voc.add_concept("subject-area-1", "Subject Area 1")
    vocabulary_repository.save(subject_area_voc)

    publication = domainfactory.publication(
        subject_area=subject_area_voc.get_concept("subject-area-1"),
        publication_type=publication_type_voc.get_concept("pub-type-1"),
    )
    dto = PublicationDto.from_publication(publication)

    store = DictStore()
    store["publication_step"] = dto.to_post_data(exclude={"journal", "contracts"})
    store.save()

    sut = PublicationStep()
    ctx = sut.get_context_data(request_factory.get("/"), store)

    pub_form = cast(PublicationForm, ctx["publication_form"])

    assert_has_concept_choices(pub_form, "subject_area", subject_area_voc)
    assert_has_concept_choices(pub_form, "publication_type", publication_type_voc)


@pytest.mark.django_db
def test__publication_step__corresponding_author_in_store__new_corresponding_author_in_request__prefers_new_author() -> (
    None
):
    corresponding_author = domainfactory.author(role=Role.CORRESPONDING_AUTHOR)
    publication = domainfactory.publication()
    publication.corresponding_author = corresponding_author
    stored_dto = PublicationDto.from_publication(publication)

    new_dto = stored_dto.model_copy()
    expected_corresponding_author = domainfactory.author(role=Role.CORRESPONDING_AUTHOR)
    new_dto.corresponding_author = AuthorDto.from_author(expected_corresponding_author)

    store = DictStore()
    store["publication_step"] = stored_dto.to_post_data(exclude={"journal", "contracts"})
    store.save()

    request = request_factory.post("/", publication_step.stepdata(new_dto))

    sut = PublicationStep()
    ctx = sut.get_context_data(request, store)

    author_form: AuthorForm = ctx["author_form"]
    author_form.full_clean()
    assert_author_eq(author_form.to_author(), expected_corresponding_author)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "step_request",
    [
        request_factory.get("/"),
        request_factory.post("/", publication_step.stepdata()),
        request_factory.post("/", parse()),
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
        request_factory.post("/", parse()),
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
    form: PublicationForm, field_name: str, vocabulary: Vocabulary
) -> None:
    field = cast(forms.ChoiceField, form.fields[field_name])
    choice_names = [name for _, name in field.choices]
    assert choice_names == [c.name for c in vocabulary.concepts]
