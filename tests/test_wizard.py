from collections.abc import Callable
from typing import cast

import pytest
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.test import RequestFactory

from coda.apps.wizard import Step, Wizard


class SimpleStep(Step):
    template_name: str = "simple_template.html"


class InvalidStep(Step):
    template_name: str = "template_with_data.html"
    context: dict[str, str] = {"name": "Invalid"}

    def is_valid(self, request: HttpRequest) -> bool:
        return False


class StepWithContext(SimpleStep):
    template_name: str = "template_with_data.html"
    context: dict[str, str] = {"name": "Steven"}


def make_sut(steps: list[Step], success_url: str = "") -> Callable[..., HttpResponse]:
    return cast(Callable[..., HttpResponse], Wizard.as_view(steps=steps, success_url=success_url))


def get(
    view: Callable[..., HttpResponse], query_params: dict[str, str] | None = None
) -> HttpResponse:
    factory = RequestFactory()
    _step = 1
    if query_params:
        _step = int(query_params["step"])
    return view(factory.get("/"), step=_step)


def post(
    view: Callable[..., HttpResponse], query_params: dict[str, str] | None = None
) -> HttpResponse:
    factory = RequestFactory()
    _step = 1
    if query_params:
        _step = int(query_params["step"])
    return view(factory.post("/"), step=_step)


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

    assert_rendered_with_context(response)


def test__wizard_with_two_steps__get_step_2__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = get(sut, step(2))

    assert_rendered_with_context(response)


def test__wizard_with_two_steps__post_to_first_step__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = post(sut)

    assert_rendered_with_context(response)


def test__wizard_with_three_steps__post_to_second_step__renders_third_step() -> None:
    sut = make_sut(steps=[SimpleStep(), SimpleStep(), StepWithContext()])

    response = post(sut, step(2))

    assert_rendered_with_context(response)


def test__wizard__post_to_last_step__redirects_to_success_url() -> None:
    sut = make_sut(steps=[SimpleStep()], success_url="/success")

    response = cast(HttpResponseRedirect, post(sut))

    assert response.status_code == 302
    assert response.url == "/success"


@pytest.mark.parametrize("s", [-5, 0, 2, 5])
def test__wizard__post_to_step_out_of_bounds__renders_first_step(s: int) -> None:
    sut = make_sut(steps=[SimpleStep()])

    response = post(sut, step(s))

    assert response.content.strip() == b"Hello World"


@pytest.mark.parametrize("s", [-5, 0, 2, 5])
def test__wizard__get_step_out_of_bounds__renders_first_step(s: int) -> None:
    sut = make_sut(steps=[SimpleStep()])

    response = get(sut, step(s))

    assert response.content.strip() == b"Hello World"


def test__wizard__post_to_invalid_step__rerenders_same_step() -> None:
    sut = make_sut(steps=[InvalidStep(), SimpleStep()])

    response = post(sut, step(1))

    assert_rendered_with_context(response, "Invalid")


def test__wizard__post_to_last_step_invalid__rerenders_last_step() -> None:
    sut = make_sut(steps=[SimpleStep(), InvalidStep()])

    response = post(sut, step(2))

    assert_rendered_with_context(response, "Invalid")


def step(s: int) -> dict[str, str]:
    return {"step": str(s)}


def assert_rendered_with_context(response: HttpResponse, expected: str = "Steven") -> None:
    assert response.content.strip() == f"{expected}".encode()
