"""View mixins for shared behavior across funding request views."""

from typing import Any

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class MassImportAwareMixin:
    """Mixin for single-DOI views that need mass-import context awareness.

    Detects mass-import context by checking for ``mass_import_session_key``
    in the child session data (as stored by views in ``mass_doi_import.py``),
    rather than via URL query parameters.

    Usage::

        class MyDetailView(LoginRequiredMixin, MassImportAwareMixin, View):
            def get(self, request, session_key):
                session_data = request.session.get(session_key)
                context = {...}
                context.update(self.get_mass_import_context(session_data))
                ...

        class MySaveView(LoginRequiredMixin, MassImportAwareMixin, View):
            def post(self, request, session_key):
                session_data = request.session.get(session_key)
                response = self.redirect_if_mass_import(session_data)
                if response:
                    return response
                # ... normal save logic ...
    """

    def get_mass_import_context(self, session_data: dict[str, Any] | None) -> dict[str, Any]:
        """Return template context for mass-import mode, or empty context.

        When the session contains a ``mass_import_session_key``, the view
        is being accessed from a mass-import workflow and the UI should
        show a "Back to mass import" link instead of the normal Cancel/Save
        buttons.

        Returns a dict with ``is_mass_import`` and (when applicable)
        ``mass_import_back_url`` keys.
        """
        mass_import_key = (session_data or {}).get("mass_import_session_key")
        if mass_import_key is not None:
            return {
                "is_mass_import": True,
                "mass_import_back_url": reverse(
                    "fundingrequests:mass_doi_preview",
                    kwargs={"session_key": mass_import_key},
                ),
            }
        return {"is_mass_import": False}

    def redirect_if_mass_import(self, session_data: dict[str, Any] | None) -> HttpResponse | None:
        """Redirect to mass preview if in mass-import mode, else return None.

        Returns an ``HttpResponse`` (redirect) when the session indicates
        mass-import context, allowing the caller to short-circuit and return
        the redirect early. Returns ``None`` when not in mass-import mode.
        """
        mass_import_key = (session_data or {}).get("mass_import_session_key")
        if mass_import_key is not None:
            return redirect(
                "fundingrequests:mass_doi_preview",
                session_key=mass_import_key,
            )
        return None
