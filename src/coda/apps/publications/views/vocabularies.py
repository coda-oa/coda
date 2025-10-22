from collections.abc import Sequence

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


def get_posted_concepts(request: HttpRequest, key: str) -> set[str]:
    return {c for c in request.POST.getlist(key) if c}


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

    limited = LimitedVocabulary(
        id=None,
        base_vocabulary=base_vocabulary,
        name=f"{base_vocabulary.name} (limited)",
        version=base_vocabulary.version,
    )

    # If this is a POST request (from HTMX moves), apply the posted state
    if request.method == "POST":
        posted_disallowed = get_posted_concepts(request, "disallowed_concepts")

        # Reset current disallowed and apply posted disallowed list
        limited.clear_disallowed()
        for concept_id in posted_disallowed:
            limited.disallow(concept_id)

    # Now build trees from the in-memory state (no DB writes)
    allowed_tree, forbidden_tree = limited.get_concept_trees()

    return render(
        request,
        "publications/vocabulary.html",
        {
            "vocabulary": limited,
            "allowed_tree": allowed_tree,
            "forbidden_tree": forbidden_tree,
            "base_vocabulary_id": pk,
        },
    )


@login_required
@breadcrumb("Edit Limited Vocabulary", parent_url_name="publications:vocabularies")
def edit_limited(request: HttpRequest, pk: int) -> HttpResponse:
    vocabulary = vocabulary_repository.get_limited_by_id(VocabularyId(pk))
    allowed_tree, forbidden_tree = vocabulary.get_concept_trees()
    return render(
        request,
        "publications/vocabulary.html",
        {
            "vocabulary": vocabulary,
            "allowed_tree": allowed_tree,
            "forbidden_tree": forbidden_tree,
        },
    )


@login_required
def save_vocabularies(request: HttpRequest) -> HttpResponse:
    vocabulary_id = request.POST.get("vocabulary_id")

    if vocabulary_id and vocabulary_id != "None":
        # Edit flow - load existing limited vocabulary
        vocabulary = get_vocabulary(request)
        vocabulary.name = request.POST["vocabulary_name"]
    else:
        # Create flow - create new limited vocabulary from base
        base_vocabulary_id = request.POST.get("base_vocabulary_id")
        if not base_vocabulary_id:
            raise ValueError("base_vocabulary_id is required for creating new limited vocabulary")

        base_vocabulary = vocabulary_repository.get_by_id(VocabularyId(int(base_vocabulary_id)))
        vocabulary = LimitedVocabulary(
            id=None,
            base_vocabulary=base_vocabulary,
            name=request.POST["vocabulary_name"],
            version=base_vocabulary.version,
        )

    # Apply posted disallowed concepts (final state from client)
    posted_disallowed = get_posted_concepts(request, "disallowed_concepts")
    vocabulary.clear_disallowed()
    for concept_id in posted_disallowed:
        vocabulary.disallow(concept_id)

    # Persist once when user clicks Save
    vocabulary_repository.save(vocabulary)

    return redirect("publications:vocabularies")


def _move_concepts_between_lists(
    request: HttpRequest, selected_concepts_param: str, move_from_allowed_to_forbidden: bool
) -> HttpResponse:
    # Load the vocabulary (handles both create and edit scenarios)
    vocabulary = get_vocabulary_for_moves(request)

    # Reconstruct current in-memory state from full lists posted by the client
    posted_disallowed = get_posted_concepts(request, "disallowed_concepts")

    # Reset vocabulary to match posted state
    vocabulary.clear_disallowed()
    for concept_id in posted_disallowed:
        vocabulary.disallow(concept_id)

    # Now apply the user's current selection/move on top of that state
    selected_concepts = get_posted_concepts(request, selected_concepts_param)
    if move_from_allowed_to_forbidden:
        for concept_id in selected_concepts:
            # ensure it's disallowed
            vocabulary.disallow(concept_id)
    else:
        for concept_id in selected_concepts:
            vocabulary.allow(concept_id)

    # Build trees from in-memory state (no DB writes)
    allowed_tree, forbidden_tree = vocabulary.get_concept_trees()

    # Pass base_vocabulary_id for create flow
    context = {
        "vocabulary": vocabulary,
        "allowed_tree": allowed_tree,
        "forbidden_tree": forbidden_tree,
    }

    # Add base_vocabulary_id if this is a create flow
    if vocabulary.id is None:
        base_vocabulary_id = request.POST.get("base_vocabulary_id")
        if base_vocabulary_id:
            context["base_vocabulary_id"] = int(base_vocabulary_id)

    return render(
        request,
        "publications/vocabulary_table.html",
        context,
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


def get_vocabulary_for_moves(request: HttpRequest) -> LimitedVocabulary:
    vocabulary_id = request.POST.get("vocabulary_id")

    # Edit Limited Vocabulary
    if vocabulary_id and vocabulary_id != "None":
        return vocabulary_repository.get_limited_by_id(VocabularyId(int(vocabulary_id)))
    # Create Limited Vocabulary
    else:
        base_vocabulary_id = request.POST.get("base_vocabulary_id")
        if not base_vocabulary_id:
            raise ValueError("Either vocabulary_id or base_vocabulary_id must be provided")

        base_vocabulary = vocabulary_repository.get_by_id(VocabularyId(int(base_vocabulary_id)))
        return LimitedVocabulary(
            id=None,
            base_vocabulary=base_vocabulary,
            name=f"{base_vocabulary.name} (limited)",
            version=base_vocabulary.version,
        )
