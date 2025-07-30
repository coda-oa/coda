from typing import Any, cast

from django.http import HttpRequest
from django.test import RequestFactory
from django.utils.safestring import mark_safe

from coda.apps.fundingrequests.views.wizard.steps.composed_step import ComposedStep
from coda.apps.wizard import StepLike, Store
from tests.test_wizard import DictStore


class StepStub(StepLike):
    def __init__(self, name: str, valid: bool = True) -> None:
        self.name = name
        self.valid = valid
        self.is_done = False

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return self.valid

    def done(self, request: HttpRequest, store: Store) -> None:
        self.is_done = True

    def render(self, request: HttpRequest, store: Store, extras: dict[str, Any]) -> str:
        return mark_safe(f"<div>{self.name} rendered</div>")


class _TestComposedStep(ComposedStep):
    template_name = "simplified_composed_step.html"

    def __init__(self) -> None:
        super().__init__()
        self.substeps = [StepStub("step1"), StepStub("step2"), StepStub("step3")]


_request_factory = RequestFactory()


def test__composed_step_is_valid_when_all_substeps_are_valid() -> None:
    sut = _TestComposedStep()
    request = _request_factory.get("/")
    store = DictStore()

    assert sut.is_valid(request, store) is True


def test__composed_step_done_calls_done_on_all_substeps() -> None:
    sut = _TestComposedStep()
    request = _request_factory.get("/")
    store = DictStore()

    sut.done(request, store)

    for step in sut.substeps:
        assert cast(StepStub, step).is_done is True


def test__composed_step_render__chains_render_of_substeps() -> None:
    sut = _TestComposedStep()
    request = _request_factory.get("/")
    store = DictStore()

    rendered = sut.render(request, store, {})
    rendered = rendered.strip().replace("\n", "")
    assert rendered == "<div>step1 rendered</div><div>step2 rendered</div><div>step3 rendered</div>"
