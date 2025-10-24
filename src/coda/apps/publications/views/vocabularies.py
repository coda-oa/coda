from collections.abc import Sequence
from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publications.services import vocabularies
from coda.apps.publications.services.vocabularies import build_concept_trees, ConceptTreeNode
from coda.apps.views import EntityListView
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyConcept,
    VocabularyId,
    VocabularyProtocol,
)


ConceptPair = tuple[VocabularyConcept | None, VocabularyConcept | None]


@dataclass
class UITreeNode:
    """Tree node with UI-specific annotations for template rendering"""

    concept: VocabularyConcept
    children: list["UITreeNode"]
    is_allowed: bool  # For template: whether to show checkbox or just label
    zebra_index: int  # For template: sequential index for zebra striping
    level: int  # For template: hierarchy level (1=root, 2=children, etc.)


def annotate_trees_for_ui(
    allowed_tree: list[ConceptTreeNode],
    forbidden_tree: list[ConceptTreeNode],
    vocabulary: LimitedVocabulary,
) -> tuple[list[UITreeNode], list[UITreeNode], int, set[int], set[int]]:
    """Add UI-specific annotations to concept trees for template rendering.

    This handles the presentation logic of when to show checkboxes vs labels.
    - Allowed tree: show checkbox for allowed concepts, label for forbidden ones
    - Forbidden tree: show checkbox for forbidden concepts, label for allowed ones

    Also adds sequential zebra_index for proper striping across nested lists.

    Returns:
        tuple: (ui_allowed_tree, ui_forbidden_tree, overall_max_level, allowed_levels_with_checkboxes, forbidden_levels_with_checkboxes)
    """

    def annotate_tree(
        tree: list[ConceptTreeNode], is_allowed_tree: bool
    ) -> tuple[list[UITreeNode], set[int]]:
        zebra_counter = [0]  # Use list to make it mutable in nested function
        levels_with_checkboxes = set()  # Track which levels actually have checkboxes

        def annotate_node(node: ConceptTreeNode, level: int = 1) -> UITreeNode:
            zebra_counter[0] += 1
            current_index = zebra_counter[0]

            is_concept_allowed = vocabulary.is_concept_allowed(node.concept.concept_id)
            # Show checkbox if this concept belongs to this tree's purpose
            show_checkbox = is_concept_allowed if is_allowed_tree else not is_concept_allowed

            # Track levels that have actual checkboxes
            if show_checkbox:
                levels_with_checkboxes.add(level)

            return UITreeNode(
                concept=node.concept,
                children=[annotate_node(child, level + 1) for child in node.children],
                is_allowed=show_checkbox,
                zebra_index=current_index,
                level=level,
            )

        annotated_nodes = [annotate_node(node) for node in tree]
        return annotated_nodes, levels_with_checkboxes

    ui_allowed_tree, allowed_levels_with_checkboxes = annotate_tree(allowed_tree, True)
    ui_forbidden_tree, forbidden_levels_with_checkboxes = annotate_tree(forbidden_tree, False)

    # Calculate overall max level from all levels that have checkboxes
    all_levels_with_checkboxes = allowed_levels_with_checkboxes | forbidden_levels_with_checkboxes
    overall_max_level = max(all_levels_with_checkboxes) if all_levels_with_checkboxes else 0

    return (
        ui_allowed_tree,
        ui_forbidden_tree,
        overall_max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    )


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
    allowed_tree, forbidden_tree = build_concept_trees(limited)
    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = annotate_trees_for_ui(allowed_tree, forbidden_tree, limited)

    return render(
        request,
        "publications/vocabulary.html",
        {
            "vocabulary": limited,
            "allowed_tree": ui_allowed_tree,
            "forbidden_tree": ui_forbidden_tree,
            "max_level": max_level,
            "level_range": range(1, max_level + 1),
            "allowed_level_range": sorted(allowed_levels_with_checkboxes),
            "forbidden_level_range": sorted(forbidden_levels_with_checkboxes),
            "base_vocabulary_id": pk,
        },
    )


@login_required
@breadcrumb("Edit Limited Vocabulary", parent_url_name="publications:vocabularies")
def edit_limited(request: HttpRequest, pk: int) -> HttpResponse:
    vocabulary = vocabulary_repository.get_limited_by_id(VocabularyId(pk))
    allowed_tree, forbidden_tree = build_concept_trees(vocabulary)
    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = annotate_trees_for_ui(allowed_tree, forbidden_tree, vocabulary)
    return render(
        request,
        "publications/vocabulary.html",
        {
            "vocabulary": vocabulary,
            "allowed_tree": ui_allowed_tree,
            "forbidden_tree": ui_forbidden_tree,
            "max_level": max_level,
            "level_range": range(1, max_level + 1),
            "allowed_level_range": sorted(allowed_levels_with_checkboxes),
            "forbidden_level_range": sorted(forbidden_levels_with_checkboxes),
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
    allowed_tree, forbidden_tree = build_concept_trees(vocabulary)
    (
        ui_allowed_tree,
        ui_forbidden_tree,
        max_level,
        allowed_levels_with_checkboxes,
        forbidden_levels_with_checkboxes,
    ) = annotate_trees_for_ui(allowed_tree, forbidden_tree, vocabulary)

    # Pass base_vocabulary_id for create flow
    context = {
        "vocabulary": vocabulary,
        "allowed_tree": ui_allowed_tree,
        "forbidden_tree": ui_forbidden_tree,
        "max_level": max_level,
        "level_range": range(1, max_level + 1),
        "allowed_level_range": sorted(allowed_levels_with_checkboxes),
        "forbidden_level_range": sorted(forbidden_levels_with_checkboxes),
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
