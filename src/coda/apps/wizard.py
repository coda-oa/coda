from abc import ABC
from collections.abc import Callable, Iterable
from typing import Any, Generic, NamedTuple, Protocol, TypeVar, cast, overload

from django.forms import Form
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

KT = TypeVar("KT")
VT = TypeVar("VT", covariant=True)


class SupportsKeysAndGetItem(Protocol, Generic[KT, VT]):
    def __getitem__(self, key: KT) -> VT:
        ...

    def keys(self) -> Iterable[KT]:
        ...


class Store(Protocol):
    def save(self) -> None:
        ...

    def __getitem__(self, key: str) -> Any:
        ...

    def __setitem__(self, key: str, value: Any) -> None:
        ...

    @overload
    def get(self, key: str, default: Any, /) -> Any:
        ...

    @overload
    def get(self, key: str, /) -> Any | None:
        ...

    @overload
    def update(self, other: SupportsKeysAndGetItem[str, Any], /, **kwargs: Any) -> None:
        pass

    @overload
    def update(self, other: Iterable[tuple[str, Any]], **kwargs: Any) -> None:
        ...

    @overload
    def update(self, **kwargs: Any) -> None:
        ...

    def clear(self) -> None:
        ...


class SessionStore(Store):
    def __init__(self, store_name: str, request: HttpRequest) -> None:
        self.request = request
        self.store_name = store_name

    def save(self) -> None:
        self.request.session.save()

    @property
    def data(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.request.session.setdefault(self.store_name, {}))

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def update(
        self,
        other: SupportsKeysAndGetItem[str, Any] | Iterable[tuple[str, Any]] = (),
        /,
        **kwargs: Any,
    ) -> None:
        self.data.update(other, **kwargs)

    def clear(self) -> None:
        if self.store_name in self.request.session:
            self.request.session[self.store_name] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Step(ABC):
    template_name: str
    context: dict[str, str]

    def __init__(self) -> None:
        if not hasattr(self, "template_name"):
            raise AttributeError("Step must have a template_name attribute")

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return True

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        if hasattr(self, "context"):
            return self.context
        return {}

    def done(self, request: HttpRequest, store: Store) -> None:
        pass


class FormStep(Step, ABC):
    form_class: type[Form]

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        form_data = request.POST if request.method == "POST" else None
        return super().get_context_data(request, store) | {"form": self.form_class(form_data)}

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        form = self.form_class(request.POST)
        return form.is_valid()


StoreFactory = Callable[[str, HttpRequest], Store]


class Stepper(NamedTuple):
    current: int
    total: int


class Wizard(View):
    steps: list[Step] = []
    success_url: str = ""
    store_name: str = ""
    store_factory: StoreFactory = None  # type: ignore

    def get_success_url(self) -> str:
        return self.success_url

    def get_store(self) -> Store:
        return self.store_factory(self.store_name, self.request)

    def index(self) -> int:
        step = int(self.get_store().get("step", 0))
        if self._out_of_bounds(step):
            step = 0

        return step

    def complete(self, **kwargs: Any) -> None:
        pass

    def prepare(self, request: HttpRequest) -> None:
        pass

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        self.get_store().clear()
        self.get_store().save()
        self.prepare(request)
        return self._render_step(request, self.index())

    def post(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        next_index = self.determine_next_index(request)
        store = self.get_store()

        response: HttpResponse
        if self.is_last(next_index):
            self.complete(**kwargs)
            response = redirect(self.get_success_url())
            store.clear()
        else:
            next_index = self.ensure_in_bounds(next_index)
            response = self._render_step(request, next_index)
            store["step"] = next_index

        store.save()
        return response

    def ensure_in_bounds(self, index: int) -> int:
        if self._out_of_bounds(index):
            index = self.index()
        return index

    def is_last(self, index: int) -> bool:
        return index == len(self.steps)

    def determine_next_index(self, request: HttpRequest) -> int:
        match request.POST.get("action"):
            case "next":
                next_index = self.next_index()
            case "back":
                next_index = self.index() - 1
            case _:
                next_index = self.index()
        return next_index

    def next_index(self) -> int:
        current_index = self.index()
        current_step = self.steps[current_index]
        store = self.get_store()
        if current_step.is_valid(self.request, store):
            current_step.done(self.request, store)
            current_index = current_index + 1

        return current_index

    def _out_of_bounds(self, current_step: int) -> bool:
        return current_step < 0 or current_step >= len(self.steps)

    def _render_step(self, request: HttpRequest, index: int) -> HttpResponse:
        step = self.steps[index]
        context = step.get_context_data(request, self.get_store())
        context["stepper"] = Stepper(index + 1, len(self.steps))
        return render(request, step.template_name, context)
