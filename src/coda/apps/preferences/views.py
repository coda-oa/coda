from collections.abc import Iterable
from itertools import zip_longest
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic.edit import UpdateView

from coda.apps.preferences.forms import GlobalPreferencesForm
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.repositories import vocabulary_repository
from coda.vocabulary import ConceptId, Vocabulary, VocabularyConcept, VocabularyId


class GlobalPreferencesUpdateView(
    LoginRequiredMixin,
    SuccessMessageMixin[GlobalPreferencesForm],
    UpdateView[GlobalPreferences, GlobalPreferencesForm],
):
    model = GlobalPreferences
    form_class = GlobalPreferencesForm
    template_name = "preferences/global.html"
    success_message = "Preferences updated"
    success_url = reverse_lazy("preferences:global_preferences")

    def get_object(self, queryset: models.QuerySet[Any, Any] | None = None) -> GlobalPreferences:
        settings, _ = GlobalPreferences.objects.get_or_create()
        return settings


@login_required
def vocabulary_view(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "preferences/vocabulary.html",
        {
            "vocabularies": vocabulary_repository.all(),
        },
    )


@login_required
@require_GET
def select_vocabulary(request: HttpRequest) -> HttpResponse:
    vocabulary_id = VocabularyId(int(request.GET["selected-vocabulary"]))
    vocabulary = vocabulary_repository.get_by_id(vocabulary_id)
    return render(
        request,
        "preferences/vocabulary_table.html",
        {"selected_vocabulary": vocabulary, "concept_pairs": concept_pairs(vocabulary)},
    )


@login_required
@require_POST
def move_to_forbidden(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)

    disallowed_concept = request.POST["disallow"]
    vocabulary.set_forbidden(ConceptId(disallowed_concept))
    vocabulary_repository.save(vocabulary)

    return render(
        request,
        "preferences/vocabulary_table.html",
        {"selected_vocabulary": vocabulary, "concept_pairs": concept_pairs(vocabulary)},
    )


@login_required
@require_POST
def move_to_allowed(request: HttpRequest) -> HttpResponse:
    vocabulary = get_vocabulary(request)

    allowed_concept = request.POST["allow"]
    vocabulary.set_allowed(ConceptId(allowed_concept))
    vocabulary_repository.save(vocabulary)

    return render(
        request,
        "preferences/vocabulary_table.html",
        {"selected_vocabulary": vocabulary, "concept_pairs": concept_pairs(vocabulary)},
    )


def get_vocabulary(request: HttpRequest) -> Vocabulary:
    v_id = VocabularyId(int(request.POST["vocabulary_id"]))
    v_name = request.POST["vocabulary_name"]
    v_version = request.POST["vocabulary_version"]
    vocabulary = Vocabulary(id=v_id, name=v_name, version=v_version)

    allowed = get_allowed_concepts(request)
    forbidden = get_forbidden_concept(request)
    add_allowed(vocabulary, allowed)
    add_forbidden(vocabulary, forbidden)

    return vocabulary


def add_allowed(vocabulary: Vocabulary, allowed: Iterable[tuple[str, str, str]]) -> None:
    for a_id, a_name, a_description in allowed:
        vocabulary.add_concept(id=ConceptId(a_id), name=a_name, description=a_description)


def add_forbidden(vocabulary: Vocabulary, forbidden: Iterable[tuple[str, str, str]]) -> None:
    for f_id, f_name, f_description in forbidden:
        vocabulary.add_concept(
            id=ConceptId(f_id), name=f_name, description=f_description, is_allowed=False
        )


def get_allowed_concepts(request: HttpRequest) -> Iterable[tuple[str, str, str]]:
    return zip(
        request.POST.getlist("allowed_ids"),
        request.POST.getlist("allowed_names"),
        request.POST.getlist("allowed_descriptions"),
    )


def get_forbidden_concept(request: HttpRequest) -> Iterable[tuple[str, str, str]]:
    return zip(
        request.POST.getlist("forbidden_ids"),
        request.POST.getlist("forbidden_names"),
        request.POST.getlist("forbidden_descriptions"),
    )


def concept_pairs(
    vocabulary: Vocabulary,
) -> Iterable[tuple[VocabularyConcept | None, VocabularyConcept | None]]:
    allowed_concepts = vocabulary.allowed_concepts()
    forbidden_concepts = vocabulary.forbidden_concepts()
    return zip_longest(allowed_concepts, forbidden_concepts, fillvalue=None)
