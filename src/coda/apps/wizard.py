from abc import ABC
from typing import Any

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


class Wizard(View):
    steps: list[Step] = []
    success_url: str = ""

    def get_success_url(self) -> str:
        return self.success_url

    def get(self, request: HttpRequest) -> HttpResponse:
        index = self.current_step_index(request)
        if self._out_of_bounds(index):
            index = 0
        return self._render_step(request, index)

    def current_step_index(self, request: HttpRequest) -> int:
        step = request.GET.get("step", 1)
        return int(step) - 1

    def current_step(self, request: HttpRequest) -> int:
        return int(request.GET.get("step", 1))

    def post(self, request: HttpRequest) -> HttpResponse:
        current_index = self.current_step_index(request)
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
        return render(request, step.template_name, step.get_context_data(request))
