from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic.edit import UpdateView

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.preferences.forms import CrossrefAccessForm, GlobalPreferencesForm
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.fundingrequest.services.doi_import import crossref_access


@breadcrumb("Coda Global Preferences")
class GlobalPreferencesUpdateView(
    LoginRequiredMixin,
    UpdateView[GlobalPreferences, GlobalPreferencesForm],
):
    """The settings page: renders both cards, handles the general form."""

    model = GlobalPreferences
    form_class = GlobalPreferencesForm
    template_name = "preferences/global.html"
    success_url = reverse_lazy("preferences:global_preferences")

    def get_object(self, queryset: models.QuerySet[Any, Any] | None = None) -> GlobalPreferences:
        settings, _ = GlobalPreferences.objects.get_or_create()
        return settings

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        prefs = self.get_object()
        context["crossref_form"] = CrossrefAccessForm(instance=prefs)
        # Card state reflects what is *stored*, not what a bound form may
        # carry: the form instance can hold typed-but-unsaved input, so it
        # must never decide whether a key exists.
        context["has_stored_token"] = bool(prefs.crossref_plus_api_token)
        context["token_rejected"] = prefs.crossref_plus_api_token_valid is False
        return context


class CrossrefSettingsUpdateView(
    LoginRequiredMixin,
    UpdateView[GlobalPreferences, CrossrefAccessForm],
):
    """POST endpoint for the Crossref card, swapped in place via htmx.

    htmx submits this card with ``hx-post``/``hx-target="#crossref-card"``;
    on invalid input only the card fragment is returned, so the browser
    stays on /preferences/ and the rest of the page is untouched. On
    success, ``HX-Redirect`` makes htmx navigate to the preferences page
    (a plain 302 would make htmx inject that page into the card). A non-htmx
    (no-JS) POST renders the full page instead of the fragment.
    """

    model = GlobalPreferences
    form_class = CrossrefAccessForm
    template_name = "preferences/global.html"  # only used by the no-JS fallback
    success_url = reverse_lazy("preferences:global_preferences")

    def get_object(self, queryset: models.QuerySet[Any, Any] | None = None) -> GlobalPreferences:
        settings, _ = GlobalPreferences.objects.get_or_create()
        return settings

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return redirect(self.success_url)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_stored_token"] = self._stored_token
        context["token_rejected"] = self.get_object().crossref_plus_api_token_valid is False
        return context

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # Read storage before form.save() may change it.
        self._stored_token = bool(self.get_object().crossref_plus_api_token)
        self.object = self.get_object()
        form = CrossrefAccessForm(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
            messages.success(request, "Crossref settings updated")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=200)
                response["HX-Redirect"] = str(self.success_url)
                return response
            return redirect(self.success_url)

        if request.headers.get("HX-Request") != "true":
            # No-JS fallback: render the full page with the bound form.
            return self.render_to_response(
                self.get_context_data(
                    form=GlobalPreferencesForm(instance=self.object), crossref_form=form
                )
            )
        # htmx: swap only the card fragment.
        response = render(
            request,
            "preferences/partials/crossref_card.html",
            self.get_context_data(crossref_form=form),
        )
        return response

    _stored_token: bool = False


@login_required
@require_POST
def crossref_token_status(request: HttpRequest) -> HttpResponse:
    """HTMX endpoint: check the currently stored Crossref key on demand.

    Re-checks the stored key against Crossref every time it is called, so
    an expired key is reported even long after it was saved. Renders a
    fragment for swapping into the Crossref card footer of the preferences
    page.
    """
    status, message, has_token = crossref_access.check_stored_token()
    css_status = {"verified": "success", "rejected": "error"}.get(status, "warning")
    return render(
        request,
        "preferences/crossref_token_status.html",
        {
            "status": status,
            "message": message,
            "has_token": has_token,
            "css_status": css_status,
        },
    )
