from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView

from coda.apps.preferences.forms import GlobalPreferencesForm
from coda.apps.preferences.models import GlobalPreferences


class GlobalPreferencesUpdateView(
    UpdateView[GlobalPreferences, GlobalPreferencesForm], LoginRequiredMixin
):
    model = GlobalPreferences
    form_class = GlobalPreferencesForm
    template_name = "generic_form_view.html"
    success_url = reverse_lazy("preferences:global_preferences")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return {"title": "CODA Preferences"} | super().get_context_data(**kwargs)

    def get_object(self, queryset: models.QuerySet[Any, Any] | None = None) -> GlobalPreferences:
        settings, _ = GlobalPreferences.objects.get_or_create()
        return settings
