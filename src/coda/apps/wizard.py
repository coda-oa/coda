from abc import ABC
from typing import Any

from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View


class Step(ABC):
    template_name: str
    context: dict[str, str] = {}

    def __init__(self) -> None:
        if not hasattr(self, "template_name"):
            raise AttributeError("Step must have a template_name attribute")

    def is_valid(self, request: HttpRequest) -> bool:
        return True

    def get_context_data(self, request: HttpRequest) -> dict[str, Any]:
        return self.context


class FormStep(Step, ABC):
    form_class: type[Form]

    def get_context_data(self, request: HttpRequest) -> dict[str, Any]:
        form_data = request.POST if request.method == "POST" else None
        return super().get_context_data(request) | {"form": self.form_class(form_data)}

    def is_valid(self, request: HttpRequest) -> bool:
        form = self.form_class(request.POST)
        return form.is_valid()


class Wizard(View):
    steps: list[Step] = []
    success_url: str = ""

    def get_success_url(self) -> str:
        return self.success_url

    def index(self, step: int) -> int:
        return step - 1

    def get(self, request: HttpRequest, step: int = 1) -> HttpResponse:
        index = self.index(step)
        if self._out_of_bounds(index):
            index = 0
        return self._render_step(request, index)

    def post(self, request: HttpRequest, step: int = 1) -> HttpResponse:
        current_index = self.index(step)
        if self._out_of_bounds(current_index):
            return self._render_step(request, 0)

        current_step = self.steps[current_index]
        if not current_step.is_valid(request):
            return self._render_step(request, current_index)

        next_index = current_index + 1
        if next_index == len(self.steps):
            return redirect(self.get_success_url())

        return self._render_step(request, next_index)

    def _out_of_bounds(self, current_step: int) -> bool:
        return current_step < 0 or current_step >= len(self.steps)

    def _render_step(self, request: HttpRequest, index: int) -> HttpResponse:
        step = self.steps[index]
        context = step.get_context_data(request)
        context["step"] = index + 1
        return render(request, step.template_name, context)
