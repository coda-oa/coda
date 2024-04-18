from collections.abc import Callable, Iterable
from typing import Any, cast

import pytest
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.test import RequestFactory

from coda.apps.wizard import Step, Store, StoreFactory, SupportsKeysAndGetItem, Wizard


class SimpleStep(Step):
    template_name: str = "simple_template.html"


class InvalidStep(Step):
    template_name: str = "template_with_data.html"
    context: dict[str, str] = {"name": "Invalid"}

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return False


class StepWithContext(SimpleStep):
    template_name: str = "template_with_data.html"
    context: dict[str, str] = {"name": "Steven"}


class StepperStep(Step):
    template_name: str = "stepper_template.html"


class StepWithDone(SimpleStep):
    def done(self, request: HttpRequest, store: Store) -> None:
        store["done_called"] = True


class DictStore(dict[str, Any], Store):
    def __init__(self) -> None:
        super().__init__()
        self.save_state: dict[str, Any] = {}

    def save(self) -> None:
        self.save_state = self.copy()

    def get(self, key: str, __default: Any = None) -> Any:
        return super().get(key, __default)

    def update(
        self,
        __m: SupportsKeysAndGetItem[str, Any] | Iterable[tuple[str, Any]] = (),
        /,
        **kwargs: Any,
    ) -> None:
        super().update(__m, **kwargs)

    def was_saved_with(self, expected: dict[str, Any]) -> bool:
        return all(
            key in self.save_state and self.save_state[key] == value
            for key, value in expected.items()
        ) and len(self.save_state) == len(expected)

    def clear(self) -> None:
        super().clear()

    def reset_save_state(self) -> None:
        self.save_state = {}


class SingletonDictStoreFactory:
    store_name: str = ""
    store = DictStore()

    @classmethod
    def __call__(cls, store_name: str, request: HttpRequest) -> Store:
        cls.store_name = store_name
        return cast(Store, cls.store)

    @staticmethod
    def reset() -> None:
        SingletonDictStoreFactory.store_name = ""
        SingletonDictStoreFactory.store.clear()
        SingletonDictStoreFactory.store.reset_save_state()


class WizardTestImpl(Wizard):
    store_name = "wizard_test"
    success_url: str = "/success"
    store_factory: StoreFactory = SingletonDictStoreFactory()


class CompletingWizardSpy(WizardTestImpl):
    completed_state: dict[str, Any] = {}

    def __init__(self, completed_state: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.completed_state = completed_state

    def get_success_url(self) -> str:
        store = cast(DictStore, self.get_store())
        self.completed_state["success_url"] = store.get("success_url")
        return super().get_success_url()

    def complete(self, **kwargs: Any) -> None:
        store = cast(DictStore, self.get_store())
        self.completed_state["completed"] = store.get("completed")
        self.completed_state |= kwargs


@pytest.fixture(autouse=True)
def reset_store() -> None:
    SingletonDictStoreFactory.reset()


def make_sut(
    cls: type[Wizard] = WizardTestImpl,
    /,
    steps: Iterable[Step] = (),
    **kwargs: Any,
) -> Callable[..., HttpResponse]:
    return cast(Callable[..., HttpResponse], cls.as_view(steps=list(steps), **kwargs))


def get(
    view: Callable[..., HttpResponse], query_params: dict[str, str] | None = None
) -> HttpResponse:
    factory = RequestFactory()
    return view(factory.get("/", query_params))


def post(view: Callable[..., HttpResponse], data: dict[str, str] | None = None) -> HttpResponse:
    factory = RequestFactory()
    return view(factory.post("/", data))


def test__cannot_instantiate_step_without_template_name() -> None:
    class StepWithoutTemplateName(Step):
        pass

    with pytest.raises(AttributeError):
        StepWithoutTemplateName()


def test__wizard_with_step__get_renders_first_step() -> None:
    sut = make_sut(steps=[SimpleStep()])

    response = get(sut)

    assert response.content.strip() == b"Hello World"


def test__wizard_at_second_step__get_renders_first_step() -> None:
    sut = make_sut(steps=[StepWithContext(), SimpleStep()])
    _ = post(sut, next())

    response = get(sut)

    assert_rendered_with_context(response)


def test__wizard_at_first_step__adds_stepper_to_context() -> None:
    steps = [StepperStep(), SimpleStep()]
    sut = make_sut(steps=steps)

    response = get(sut)

    current = 1
    total = len(steps)
    assert_rendered_stepper(response, current, total)


def test__wizard__get__calls_prepare_before_rendering() -> None:
    class StoreReadingStep(StepWithContext):
        def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
            return {"name": store.get("prepared")}

    class PreparingWizard(WizardTestImpl):
        def prepare(self, request: HttpRequest) -> None:
            self.get_store()["prepared"] = "prepared called"

    sut = make_sut(PreparingWizard, steps=[StoreReadingStep()])

    response = get(sut)

    assert_rendered_with_context(response, "prepared called")


def test__wizard_at_second_step__adds_stepper_to_context() -> None:
    steps = [SimpleStep(), StepperStep()]
    sut = make_sut(steps=steps)

    response = post(sut, next())

    current = 2
    total = len(steps)
    assert_rendered_stepper(response, current, total)


def test__wizard__get__clears_store() -> None:
    store = SingletonDictStoreFactory.store
    store["some_data"] = "some_value"
    store.save()
    sut = make_sut(steps=[SimpleStep()])

    _ = get(sut)

    assert store.was_saved_with({})


def test__wizard_with_step__post_next__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = post(sut, next())

    assert_rendered_with_context(response)


def test__wizard_with_step__post_next__saves_store() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    _ = post(sut, next())

    store = SingletonDictStoreFactory.store
    assert store.was_saved_with(step(1))


def test__wizard__post_with_kwargs__passes_kwargs_to_complete() -> None:
    factory = RequestFactory()
    completed_state: dict[str, Any] = {}
    sut = make_sut(CompletingWizardSpy, steps=[SimpleStep()], completed_state=completed_state)

    request = factory.post("/", next())
    _ = sut(request, some_arg="some_value")

    assert completed_state["some_arg"] == "some_value"


def test__wizard__post_next__calls_done_on_current_step() -> None:
    sut = make_sut(steps=[StepWithDone(), SimpleStep()])

    _ = post(sut, next())

    store = SingletonDictStoreFactory.store
    assert "done_called" in store.save_state


def test__wizard__post_no_action__does_not_call_done_on_current_step() -> None:
    sut = make_sut(steps=[StepWithDone()])

    _ = post(sut)

    store = SingletonDictStoreFactory.store
    assert "done_called" not in store.save_state


def test__wizard_with_step_and_context__get_renders_first_step_with_context() -> None:
    step = StepWithContext()
    sut = make_sut(steps=[step])

    response = get(sut)

    assert_rendered_with_context(response)


def test__wizard_with_two_steps__post_next_in_first_step__renders_second_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = post(sut, next())

    assert_rendered_with_context(response)


def test__wizard_with_two_steps__post_without_next_action__renders_first_step() -> None:
    sut = make_sut(steps=[SimpleStep(), StepWithContext()])

    response = post(sut)

    assert response.content.strip() == b"Hello World"


def test__wizard_with_three_steps__post_next_action_twice__renders_third_step() -> None:
    sut = make_sut(steps=[SimpleStep(), SimpleStep(), StepWithContext()])

    _ = post(sut, next())
    response = post(sut, next())

    assert_rendered_with_context(response)


def test__wizard__post_to_last_step__redirects_to_success_url() -> None:
    sut = make_sut(steps=[SimpleStep()], success_url="/success")

    response = cast(HttpResponseRedirect, post(sut, next()))

    assert response.status_code == 302
    assert response.url == "/success"


def test__wizard__post_to_last_step__clears_store() -> None:
    SingletonDictStoreFactory.store["some_data"] = "some_value"
    sut = make_sut(steps=[SimpleStep()], success_url="/success")

    _ = post(sut, next())

    assert SingletonDictStoreFactory.store.was_saved_with({})


@pytest.mark.parametrize("s", [-5, 0, 2, 5])
def test__wizard__post_to_step_out_of_bounds__renders_first_step(s: int) -> None:
    store = SingletonDictStoreFactory.store
    store["step"] = s
    sut = make_sut(steps=[SimpleStep()])

    response = post(sut)

    assert response.content.strip() == b"Hello World"


def test__wizard__post_to_invalid_step__rerenders_same_step() -> None:
    sut = make_sut(steps=[InvalidStep(), SimpleStep()])

    response = post(sut, next())

    assert_rendered_with_context(response, "Invalid")


def test__wizard__post_to_invalid_step__does_not_call_done_on_step() -> None:
    class InvalidStepWithDone(InvalidStep):
        def done(self, request: HttpRequest, store: Store) -> None:
            store["done_called"] = True

    sut = make_sut(steps=[InvalidStepWithDone(), SimpleStep()])

    _ = post(sut, next())

    store = SingletonDictStoreFactory.store
    assert "done_called" not in store.save_state


def test__wizard__post_to_last_step_invalid__rerenders_last_step() -> None:
    sut = make_sut(steps=[SimpleStep(), InvalidStep()])

    response = post(sut, next())

    assert_rendered_with_context(response, "Invalid")


def test__wizard__at_last_step__back_action__renders_previous_step() -> None:
    sut = make_sut(steps=[StepWithContext(), SimpleStep()])
    _ = post(sut, next())

    response = post(sut, back())

    assert_rendered_with_context(response)


def test__wizard__at_first_step__back_action__renders_first_step() -> None:
    sut = make_sut(steps=[StepWithContext(), SimpleStep()])

    response = post(sut, back())

    assert_rendered_with_context(response)


def test__wizard__get_and_post__pass_store_to_step() -> None:
    store = SingletonDictStoreFactory.store

    class StoringStep(Step):
        template_name: str = "template_with_data.html"

        def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
            store["context"] = "updated"
            return super().get_context_data(request, store)

        def is_valid(self, request: HttpRequest, store: Store) -> bool:
            store["valid"] = "updated"
            return True

    sut = make_sut(steps=[StoringStep(), SimpleStep()])

    _ = get(sut)
    _ = post(sut, next())

    assert all(
        key in store and store[key] == value
        for key, value in {"context": "updated", "valid": "updated"}.items()
    )


def test__wizard__on_completion__calls_complete_on_self_before_clearing_store() -> None:
    completed_state: dict[str, Any] = {}
    store = SingletonDictStoreFactory.store
    store["completed"] = "completed called"

    sut = make_sut(CompletingWizardSpy, steps=[SimpleStep()], completed_state=completed_state)
    _ = post(sut, next())

    assert store.was_saved_with({})
    assert completed_state["completed"] == "completed called"


def test__wizard__on_completion__gets_success_url_before_clearing_store() -> None:
    store = SingletonDictStoreFactory.store
    store["success_url"] = "get_success_url called"
    completed_state: dict[str, Any] = {}

    sut = make_sut(CompletingWizardSpy, steps=[SimpleStep()], completed_state=completed_state)
    _ = post(sut, next())

    store = SingletonDictStoreFactory.store
    assert completed_state["success_url"] == "get_success_url called"


def test__wizard_not_completed__post_next__does_not_call_complete() -> None:
    store = SingletonDictStoreFactory.store
    store["completed"] = True
    completed_state: dict[str, Any] = {}

    sut = make_sut(
        CompletingWizardSpy, steps=[SimpleStep(), SimpleStep()], completed_state=completed_state
    )
    _ = post(sut, next())

    store = SingletonDictStoreFactory.store
    assert "completed" not in completed_state


def test__wizard__initializes_store_with_id() -> None:
    sut = make_sut(steps=[SimpleStep()])

    _ = get(sut)

    assert SingletonDictStoreFactory.store_name == WizardTestImpl.store_name


def next() -> dict[str, str]:
    return {"action": "next"}


def back() -> dict[str, str]:
    return {"action": "back"}


def step(s: int) -> dict[str, Any]:
    return {"step": s}


def assert_rendered_with_context(response: HttpResponse, expected: str = "Steven") -> None:
    assert response.content.strip() == f"{expected}".encode()


def assert_rendered_stepper(response: HttpResponse, current: int, total: int) -> None:
    assert_rendered_with_context(response, (str(current) + "\n" + str(total)))
