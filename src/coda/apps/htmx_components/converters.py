from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

TData = TypeVar("TData")


def to_htmx_formset_data(data: Sequence[TData], prefix: str = "") -> dict[str, list[Any]]:
    """
    Convert a list of dataclasses, namedtuples, or dictionaries to formset data as used in HtmxDynamicFormset.
    """
    if prefix:
        prefix = f"{prefix}-"

    form_data = {prefix + "total_forms": [str(len(data))]}
    for i, form in enumerate(data, start=1):
        _dict = _convert_to_dict(form)
        for key, value in _dict.items():
            form_data[prefix + f"form-{i}-{key}"] = [value]

    return form_data


def _convert_to_dict(form: TData) -> dict[str, Any]:
    if isinstance(form, dict):
        _dict = form
    elif is_dataclass(form):
        _fields = fields(form)
        _dict = {field.name: getattr(form, field.name) for field in _fields}
    elif hasattr(form, "_asdict"):
        _dict = form._asdict()
    elif hasattr(form, "__dict__"):
        _dict = form.__dict__
    elif hasattr(form, "__slots__"):
        _dict = {key: getattr(form, key) for key in form.__slots__}
    else:
        raise ValueError(f"Unsupported form type: {type(form)}")
    return _dict
