from collections.abc import Iterable, Sequence
from itertools import zip_longest

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
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
def save_vocabularies(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)
    vocabulary.name = request.POST["vocabulary_name"]

    final_forbidden_ids = set(request.POST.getlist("disallowed_concepts"))

    current_disallowed = [c.concept_id for c in vocabulary.disallowed_concepts]
    for concept_id in current_disallowed:
        vocabulary.allow(concept_id)

    for concept_id in final_forbidden_ids:
        if concept_id:
            vocabulary.disallow(concept_id)

    vocabulary_repository.save(vocabulary)

    return redirect("publications:vocabularies")


def _move_concepts_between_lists(
    request: HttpRequest, selected_concepts_param: str, move_from_allowed_to_forbidden: bool
) -> HttpResponse:
    """
    Helper function to move concepts between allowed and forbidden lists.

    Args:
        request: HTTP request containing form data
        selected_concepts_param: Parameter name containing selected concept IDs
        move_from_allowed_to_forbidden: True to move from allowed→forbidden, False for forbidden→allowed
    """
    vocabulary = get_vocabulary(request)

    # Get selected concepts to move
    selected_concepts = set(request.POST.getlist(selected_concepts_param))

    # Get current state of both lists
    current_allowed_ids = set(request.POST.getlist("allowed_concepts"))
    current_forbidden_ids = set(request.POST.getlist("disallowed_concepts"))

    # Calculate new state based on direction
    if move_from_allowed_to_forbidden:
        new_allowed_ids = current_allowed_ids - selected_concepts
        new_forbidden_ids = current_forbidden_ids.union(selected_concepts)
    else:  # move from forbidden to allowed
        new_allowed_ids = current_allowed_ids.union(selected_concepts)
        new_forbidden_ids = current_forbidden_ids - selected_concepts

    # Get concept objects for rendering
    allowed_concepts = [vocabulary.get_any_concept(cid) for cid in new_allowed_ids if cid]
    forbidden_concepts = [vocabulary.get_any_concept(cid) for cid in new_forbidden_ids if cid]

    # Return updated table (NO DATABASE SAVE)
    return render(
        request,
        "publications/vocabulary_table.html",
        {
            "vocabulary": vocabulary,
            "allowed_concepts": allowed_concepts,
            "forbidden_concepts": forbidden_concepts,
        },
    )


@login_required
@require_POST
def move_to_forbidden(request: HttpRequest) -> HttpResponse:
    return _move_concepts_between_lists(
        request,
        selected_concepts_param="allowed_concepts_check",
        move_from_allowed_to_forbidden=True,
    )


@login_required
@require_POST
def move_to_allowed(request: HttpRequest) -> HttpResponse:
    return _move_concepts_between_lists(
        request,
        selected_concepts_param="disallowed_concepts_check",
        move_from_allowed_to_forbidden=False,
    )


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
