from collections.abc import Sequence
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
from coda.apps.publications.services import vocabularies
from coda.apps.publications.services.vocabularies import build_concept_trees
from coda.apps.views import EntityListView
from coda.domain.vocabulary import (
    LimitedVocabulary,
    VocabularyId,
    VocabularyProtocol,
)


def _apply_disallowed(concept_ids: list[str], vocabulary: LimitedVocabulary) -> None:
    vocabulary.clear_disallowed()
    for concept_id in concept_ids:
        vocabulary.disallow(concept_id)


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
        form = LimitedVocabularyTargetForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest("Invalid vocabulary data")
        _apply_disallowed(form.cleaned_data["disallowed_concepts"], limited)

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
        _apply_disallowed(form.cleaned_data["disallowed_concepts"], vocabulary)
        vocabulary_repository.save(vocabulary)
        return redirect("publications:vocabularies")

    target = LimitedVocabularyTargetForm(request.POST)
    if not target.is_valid():
        return HttpResponseBadRequest("Could not resolve vocabulary from submitted data")

    vocabulary = target.vocabulary()
    vocabulary.name = request.POST.get("vocabulary_name") or vocabulary.name
    _apply_disallowed(target.cleaned_data["disallowed_concepts"], vocabulary)
    return render(
        request,
        "publications/vocabulary.html",
        _tree_context(vocabulary) | {"form": form},
    )


def _tree_context(vocabulary: LimitedVocabulary) -> dict[str, Any]:
    allowed_tree, forbidden_tree = build_concept_trees(vocabulary)
    return {
        "vocabulary": vocabulary,
        "allowed_tree": allowed_tree,
        "forbidden_tree": forbidden_tree,
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
    _apply_disallowed(form.cleaned_data["disallowed_concepts"], vocabulary)

    for concept_id in form.cleaned_data[selected_concepts_param]:
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
