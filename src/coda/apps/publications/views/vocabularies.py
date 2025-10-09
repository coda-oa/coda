from collections.abc import Iterable, Sequence
from itertools import zip_longest

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publications.services import vocabularies
from coda.apps.views import EntityListView
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)

ConceptPair = tuple[VocabularyConcept | None, VocabularyConcept | None]


@breadcrumb("Vocabularies")
class VocabularyListView(LoginRequiredMixin, EntityListView[VocabularyProtocol]):
    entity_name = "Vocabularies"
    entity_list_item_template = "publications/vocabulary_list_item.html"

    def get_entities(self, request: HttpRequest) -> Sequence[VocabularyProtocol]:
        return vocabulary_repository.all()


@login_required
@breadcrumb("Create Limited Vocabulary", parent_url_name="publications:vocabularies")
def create_limited(request: HttpRequest, pk: int) -> HttpResponse:
    base_vocabulary = vocabulary_repository.get_by_id(VocabularyId(pk))
    default_limited_name = f"{base_vocabulary.name} (limited)"
    limited = vocabulary_repository.create_limited(
        base_vocabulary_id=VocabularyId(pk), name=default_limited_name
    )
    return render(
        request,
        "publications/vocabulary.html",
        {"vocabulary": limited, "concept_pairs": concept_pairs(limited)},
    )


@login_required
@breadcrumb("Edit Limited Vocabulary", parent_url_name="publications:vocabularies")
def edit_limited(request: HttpRequest, pk: int) -> HttpResponse:
    limited = vocabulary_repository.get_limited_by_id(VocabularyId(pk))
    allowed_concepts = limited.concepts
    forbidden_concepts = limited.disallowed_concepts
    return render(
        request,
        "publications/vocabulary.html",
        {
            "vocabulary": limited,
            "concept_pairs": concept_pairs(limited),
            "allowed_concepts": allowed_concepts,
            "forbidden_concepts": forbidden_concepts,
        },
    )


@login_required
def enter_edit_title_mode(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "publications/vocabulary_edit_title.html",
        {"vocabulary": get_vocabulary(request), "editing": True},
    )


@login_required
def save_title(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)
    vocabulary.name = request.POST["vocabulary_name"]
    vocabulary_repository.save(vocabulary)

    return render(
        request,
        "publications/vocabulary_edit_title.html",
        {"vocabulary": vocabulary, "editing": False},
    )


def render_vocabulary_table(
    request: HttpRequest,
    vocabulary: LimitedVocabulary,
    concept_pairs: Iterable[ConceptPair],
) -> HttpResponse:
    return render(
        request,
        "publications/vocabulary_table.html",
        {
            "vocabulary": vocabulary,
            "concept_pairs": concept_pairs,
            "allowed_concepts": vocabulary.concepts,
            "forbidden_concepts": vocabulary.disallowed_concepts,
        },
    )


@login_required
@require_POST
def move_to_forbidden(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)

    disallowed_ids = request.POST.getlist("disallow")
    for concept_id in disallowed_ids:
        vocabulary.disallow(concept_id)

    vocabulary_repository.save(vocabulary)

    return render_vocabulary_table(request, vocabulary, concept_pairs(vocabulary))


@login_required
@require_POST
def move_to_allowed(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)

    allowed_ids = request.POST.getlist("allow")
    for concept_id in allowed_ids:
        vocabulary.allow(concept_id)

    vocabulary_repository.save(vocabulary)

    return render_vocabulary_table(request, vocabulary, concept_pairs(vocabulary))


@login_required
def request_delete(request: HttpRequest, pk: int) -> HttpResponse:
    vocabulary = vocabulary_repository.get_by_id(VocabularyId(pk))
    usage = vocabularies.get_usage(VocabularyId(pk))
    if not usage.can_be_deleted():
        return render(
            request,
            "publications/vocabulary_delete_forbidden_dialog.html",
            {"vocabulary": vocabulary, "usage": usage},
        )

    if usage.is_used():
        return render(
            request,
            "publications/vocabulary_delete_dialog.html",
            {"vocabulary": vocabulary, "usage": usage},
        )

    return delete(request, pk)


@login_required
@require_http_methods(["POST", "DELETE"])
def delete(request: HttpRequest, pk: int) -> HttpResponse:
    vocabularies.delete(VocabularyId(pk))
    return HttpResponse(status=200, headers={"HX-Redirect": reverse("publications:vocabularies")})


def get_vocabulary(request: HttpRequest) -> LimitedVocabulary:
    v_id = VocabularyId(int(request.POST["vocabulary_id"]))
    vocabulary = vocabulary_repository.get_limited_by_id(v_id)
    return vocabulary


def concept_pairs(vocabulary: LimitedVocabulary) -> Iterable[ConceptPair]:
    allowed_concepts = vocabulary.concepts
    forbidden_concepts = vocabulary.disallowed_concepts
    return zip_longest(allowed_concepts, forbidden_concepts, fillvalue=None)
