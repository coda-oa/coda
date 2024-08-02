from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import models
from django.urls import reverse_lazy
from django.views.generic.edit import UpdateView

from coda.apps.preferences.forms import GlobalPreferencesForm
from coda.apps.preferences.models import GlobalPreferences


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
