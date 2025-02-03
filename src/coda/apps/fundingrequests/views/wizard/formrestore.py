from typing import Any, TypeVar

from django.http import HttpRequest

from coda.apps.formbase import CodaFormBase
from coda.apps.htmx_components.forms import HtmxDynamicFormset

_TForm = TypeVar("_TForm", bound=CodaFormBase, covariant=True)


def restore_form(
    form_type: type[_TForm],
    request: HttpRequest,
    store_data: dict[str, Any] | None,
    **kwargs: Any,
) -> _TForm:
    """
    Create a form instance with POST data if matching keys are present, otherwise use stored data.
    If no stored data is present, create an empty form instance.
    """
    if form_type.form_posted(request.POST):
        return form_type(request.POST, **kwargs)
    elif store_data:
        return form_type(store_data, **kwargs)
    else:
        return form_type(**kwargs)


def restore_formset(
    formset_type: type[HtmxDynamicFormset[_TForm]],
    /,
    request: HttpRequest,
    *,
    store_data: list[dict[str, Any]] | None,
    prefix: str = "",
    **kwargs: Any,
) -> HtmxDynamicFormset[_TForm]:
    """
    Create a formset instance with POST data if matching keys are present, otherwise use stored data.
    If no stored data is present, create an empty formset instance.
    """

    total_forms = "total_forms"
    if prefix:
        total_forms = f"{prefix}-{total_forms}"

    if request.POST.get(total_forms):
        return formset_type(request.POST, prefix=prefix, **kwargs)
    elif store_data:
        return formset_type.from_data(store_data, **kwargs)
    else:
        return formset_type(**kwargs)
