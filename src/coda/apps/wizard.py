from abc import ABC
from typing import Any, Generic, Protocol, TypeVar, cast, overload
from collections.abc import Callable, Iterable

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

    def update(
        self,
        other: SupportsKeysAndGetItem[str, Any] | Iterable[tuple[str, Any]] = (),
        /,
        **kwargs: Any,
    ) -> None:
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
        del self.request.session[self.store_name]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Step(ABC):
    template_name: str
    context: dict[str, str] = {}

    def __init__(self) -> None:
        if not hasattr(self, "template_name"):
            raise AttributeError("Step must have a template_name attribute")

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        return True

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return self.context

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

    def get(self, request: HttpRequest) -> HttpResponse:
        self.get_store().clear()
        self.get_store().save()
        return self._render_step(request, self.index())

    def post(self, request: HttpRequest) -> HttpResponse:
        store = self.get_store()
        match request.POST.get("action"):
            case "next":
                current_step = self.steps[self.index()]
                current_step.done(request, store)
                store.save()
                next_index = self.next_index()
            case "back":
                next_index = self.index() - 1
            case _:
                next_index = self.index()

        if next_index == len(self.steps):
            response = redirect(self.get_success_url())
            store.clear()
            return response

        if self._out_of_bounds(next_index):
            next_index = self.index()

        store["step"] = next_index
        store.save()

        print(f"Storing {next_index} in session")
        return self._render_step(request, self.index())

    def next_index(self) -> int:
        current_index = self.index()
        current_step = self.steps[current_index]
        if not current_step.is_valid(self.request, self.get_store()):
            print(current_step.__class__.__name__, "is not valid", f"index: {current_index}")
            return current_index

        print(current_step.__class__.__name__, "is valid", f"index: {current_index}")
        return current_index + 1

    def _out_of_bounds(self, current_step: int) -> bool:
        return current_step < 0 or current_step >= len(self.steps)

    def _render_step(self, request: HttpRequest, index: int) -> HttpResponse:
        step = self.steps[index]
        print("Rendering step", step.__class__.__name__, f"index: {index}")
        context = step.get_context_data(request, self.get_store())
        context["step"] = index + 1
        return render(request, step.template_name, context)
