from typing import Any

from django.http import HttpRequest
from django.template.loader import render_to_string

from coda.apps.wizard import StepLike, Store


class ComposedStep(StepLike):
    template_name: str = "forms/wizard_composedstep.html"
    substeps: list[StepLike] = []

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        for step in self.substeps:
            if not step.is_valid(request, store):
                return False

        return True

    def done(self, request: HttpRequest, store: Store) -> None:
        for step in self.substeps:
            step.done(request, store)

    def render(self, request: HttpRequest, store: Store, extras: dict[str, Any]) -> str:
        steps = {"steps": [step.render(request, store, extras) for step in self.substeps]}
        return render_to_string(self.template_name, steps | extras, request=request)
