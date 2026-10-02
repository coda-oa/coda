from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.publications.forms import (
    LimitedVocabularySaveForm,
    LimitedVocabularyTargetForm,
    new_limited_vocabulary,
)
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publications.services import vocabularies, concept_tree
from coda.apps.publications.services.vocabularies import build_concept_trees
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
    concept: VocabularyConcept
    children: list["UITreeNode"]
    is_allowed: bool  # For template: whether to show checkbox or just label
    zebra_index: int  # For template: sequential index for zebra striping
    level: int  # For template: hierarchy level (1=root, 2=children, etc.)


@dataclass(frozen=True)
class AnnotatedTree:
    nodes: list["UITreeNode"]
    levels_with_checkboxes: set[int]


@dataclass(frozen=True)
class AnnotatedTrees:
    allowed_tree: list[UITreeNode]
    forbidden_tree: list[UITreeNode]
    max_level: int
    allowed_levels_with_checkboxes: set[int]
    forbidden_levels_with_checkboxes: set[int]


def _annotate_node_for_ui(
    node: concept_tree.ConceptTreeNode,
    vocabulary: LimitedVocabulary,
    is_allowed_tree: bool,
    level: int,
    zebra_counter: list[int],
    levels_with_checkboxes: set[int],
) -> UITreeNode:
    zebra_counter[0] += 1
    current_index = zebra_counter[0]

    concept_in_base = vocabulary.base_vocabulary.has_concept(node.concept.concept_id)

    show_checkbox = False
    if concept_in_base:
        is_concept_allowed = vocabulary.is_concept_allowed(node.concept.concept_id)
        show_checkbox = is_concept_allowed if is_allowed_tree else not is_concept_allowed

    if show_checkbox:
        levels_with_checkboxes.add(level)

    return UITreeNode(
        concept=node.concept,
        children=[
            _annotate_node_for_ui(
                child, vocabulary, is_allowed_tree, level + 1, zebra_counter, levels_with_checkboxes
            )
            for child in node.children
        ],
        is_allowed=show_checkbox,
        zebra_index=current_index,
        level=level,
    )


def _annotate_single_tree(
    tree: list[concept_tree.ConceptTreeNode],
    vocabulary: LimitedVocabulary,
    is_allowed_tree: bool,
) -> AnnotatedTree:
    zebra_counter = [0]
    levels_with_checkboxes: set[int] = set()

    annotated_nodes = [
        _annotate_node_for_ui(
            node, vocabulary, is_allowed_tree, 1, zebra_counter, levels_with_checkboxes
        )
        for node in tree
    ]
    return AnnotatedTree(nodes=annotated_nodes, levels_with_checkboxes=levels_with_checkboxes)


def annotate_trees_for_ui(
    allowed_tree: list[concept_tree.ConceptTreeNode],
    forbidden_tree: list[concept_tree.ConceptTreeNode],
    vocabulary: LimitedVocabulary,
) -> AnnotatedTrees:
    allowed = _annotate_single_tree(allowed_tree, vocabulary, True)
    forbidden = _annotate_single_tree(forbidden_tree, vocabulary, False)

    all_levels_with_checkboxes = allowed.levels_with_checkboxes | forbidden.levels_with_checkboxes
    overall_max_level = max(all_levels_with_checkboxes) if all_levels_with_checkboxes else 0

    return AnnotatedTrees(
        allowed_tree=allowed.nodes,
        forbidden_tree=forbidden.nodes,
        max_level=overall_max_level,
        allowed_levels_with_checkboxes=allowed.levels_with_checkboxes,
        forbidden_levels_with_checkboxes=forbidden.levels_with_checkboxes,
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

    limited = new_limited_vocabulary(base_vocabulary)

    # If this is a POST request (from HTMX moves), apply the posted state
    if request.method == "POST":
        _apply_posted_disallowed(request, limited)

    return render(
        request,
        "publications/vocabulary.html",
        _tree_context(limited),
    )


@login_required
@breadcrumb("Edit Limited Vocabulary", parent_url_name="publications:vocabularies")
def edit_limited(request: HttpRequest, pk: int) -> HttpResponse:
    vocabulary = vocabulary_repository.get_limited_by_id(VocabularyId(pk))
    return render(
        request,
        "publications/vocabulary.html",
        _tree_context(vocabulary),
    )


@login_required
@require_POST
def save_vocabularies(request: HttpRequest) -> HttpResponse:
    form = LimitedVocabularySaveForm(request.POST)
    if form.is_valid():
        vocabulary = form.vocabulary()
        vocabulary.name = form.cleaned_data["vocabulary_name"]
        _apply_posted_disallowed(request, vocabulary)
        vocabulary_repository.save(vocabulary)
        return redirect("publications:vocabularies")

    target = LimitedVocabularyTargetForm(request.POST)
    if not target.is_valid():
        return HttpResponseBadRequest("Could not resolve vocabulary from submitted data")

    vocabulary = target.vocabulary()
    vocabulary.name = request.POST.get("vocabulary_name") or vocabulary.name
    _apply_posted_disallowed(request, vocabulary)
    return render(
        request,
        "publications/vocabulary.html",
        _tree_context(vocabulary) | {"form": form},
    )


def _apply_posted_disallowed(request: HttpRequest, vocabulary: LimitedVocabulary) -> None:
    vocabulary.clear_disallowed()
    for concept_id in get_posted_concepts(request, "disallowed_concepts"):
        vocabulary.disallow(concept_id)


def _tree_context(vocabulary: LimitedVocabulary) -> dict[str, Any]:
    allowed_tree, forbidden_tree = build_concept_trees(vocabulary)
    annotated = annotate_trees_for_ui(allowed_tree, forbidden_tree, vocabulary)
    return {
        "vocabulary": vocabulary,
        "allowed_tree": annotated.allowed_tree,
        "forbidden_tree": annotated.forbidden_tree,
        "max_level": annotated.max_level,
        "level_range": range(1, annotated.max_level + 1),
        "allowed_level_range": sorted(annotated.allowed_levels_with_checkboxes),
        "forbidden_level_range": sorted(annotated.forbidden_levels_with_checkboxes),
        "base_vocabulary_id": vocabulary.base_vocabulary.id,
        "base_vocabulary_name": vocabulary.base_vocabulary.name,
    }


def _move_concepts_between_lists(
    request: HttpRequest, selected_concepts_param: str, move_from_allowed_to_forbidden: bool
) -> HttpResponse:
    form = LimitedVocabularyTargetForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Could not resolve vocabulary from submitted data")

    vocabulary = form.vocabulary()
    _apply_posted_disallowed(request, vocabulary)

    for concept_id in get_posted_concepts(request, selected_concepts_param):
        if move_from_allowed_to_forbidden:
            vocabulary.disallow(concept_id)
        else:
            vocabulary.allow(concept_id)

    return render(request, "publications/vocabulary_table.html", _tree_context(vocabulary))


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
@require_POST
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
