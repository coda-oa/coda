from collections.abc import Callable
from typing import cast
from urllib.parse import urlencode

import pytest
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.test import RequestFactory
from django.views import View


class Step:
    template_name: str
    context: dict[str, str] = {}

    def __init__(self) -> None:
        if not hasattr(self, "template_name"):
            raise AttributeError("Step must have a template_name attribute")

    def get_context_data(self) -> dict[str, str]:
        return self.context


class SimpleStep(Step):
    template_name: str = "simple_template.html"


class StepWithContext(SimpleStep):
    template_name: str = "template_with_data.html"
    context: dict[str, str] = {"name": "Steven"}


class Wizard(View):
    steps: list[SimpleStep] = []

    def get(self, request: HttpRequest) -> HttpResponse:
        index = self.current_step(request)
        return self.render_step(request, index)

    def render_step(self, request: HttpRequest, index: int) -> HttpResponse:
        step = self.steps[index]
        return render(request, step.template_name, step.get_context_data())

    def current_step(self, request: HttpRequest) -> int:
        step = request.GET.get("step", 1)
        return int(step) - 1

    def post(self, request: HttpRequest) -> HttpResponse:
        return self.render_step(request, self.current_step(request) + 1)


def make_sut(steps: list[SimpleStep]) -> Callable[..., HttpResponse]:
    return cast(Callable[..., HttpResponse], Wizard.as_view(steps=steps))


def get(
    view: Callable[..., HttpResponse], query_params: dict[str, str] | None = None
) -> HttpResponse:
    factory = RequestFactory()
    return view(factory.get("/", query_params))


def post(
    view: Callable[..., HttpResponse], query_params: dict[str, str] | None = None
) -> HttpResponse:
    factory = RequestFactory()
    query_string = f"?{urlencode(query_params)} " if query_params else ""
    return view(factory.post("/" + query_string))


def test__cannot_instantiate_step_without_template_name() -> None:
    class StepWithoutTemplateName(Step):
        pass

    with pytest.raises(AttributeError):
        StepWithoutTemplateName()


def test__wizard_with_step__get_renders_first_step() -> None:
    sut = make_sut([SimpleStep()])

    response = get(sut)

    assert response.content.strip() == b"Hello World"


def test__wizard_with_step_and_context__get_renders_first_step_with_context() -> None:
    step = StepWithContext()
    sut = make_sut(steps=[step])

    response = get(sut)

    assert_rendered_content_with_context(response)


def test__wizard_with_two_steps__get_step_2__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = get(sut, {"step": "2"})

    assert_rendered_content_with_context(response)


def test__wizard_with_two_steps__post_to_first_step__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = post(sut)

    assert_rendered_content_with_context(response)


def test__wizard_with_three_steps__post_to_second_step__renders_third_step() -> None:
    sut = make_sut(steps=[SimpleStep(), SimpleStep(), StepWithContext()])

    response = post(sut, {"step": "2"})

    assert_rendered_content_with_context(response)


def assert_rendered_content_with_context(response: HttpResponse) -> None:
    assert response.content.strip() == b"Hello Steven"
