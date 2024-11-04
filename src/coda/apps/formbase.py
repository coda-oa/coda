import datetime
import enum
from collections.abc import Mapping
from typing import Any, get_args

from django import forms
from django.forms.renderers import BaseRenderer
from django.forms.utils import ErrorList
from pydantic import BaseModel


class CodaFormBase(forms.Form):
    """
    Base class for forms that adds the `aria-invalid` attribute to fields with errors.
    """

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        auto_id: bool | str = True,
        prefix: str | None = None,
        initial: Mapping[str, Any] | None = None,
        error_class: type[ErrorList] = ErrorList,
        label_suffix: str | None = None,
        empty_permitted: bool = False,
        field_order: list[str] | None = None,
        use_required_attribute: bool | None = None,
        renderer: BaseRenderer | None = None,
    ) -> None:
        super().__init__(
            data,
            files,  # type: ignore
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            field_order,
            use_required_attribute,
            renderer,
        )

        for field in self.errors:
            attrs = self[field].field.widget.attrs
            attrs["aria-invalid"] = "true"


def pydantic_form(model: type[BaseModel]) -> type[forms.Form]:
    type_to_form_fields: dict[type, type[forms.Field]] = {
        int: forms.IntegerField,
        float: forms.FloatField,
        str: forms.CharField,
        bool: forms.BooleanField,
        datetime.date: forms.DateField,
        datetime.datetime: forms.DateTimeField,
        enum.Enum: forms.ChoiceField,
    }

    declared_fields: dict[str, forms.Field] = {}
    for field_name, field_info in model.model_fields.items():
        if field_info.annotation is None:
            raise ValueError(f"Field {field_name} has no type annotation")

        t_field = field_info.annotation
        args = get_args(t_field)
        if args:
            types = tuple(t for t in get_args(t_field) if t is not type(None))
            if len(types) != 1:
                raise ValueError(f"Field {field_name} has unsupported type {field_info.annotation}")

            t_field = types[0]

        if issubclass(t_field, enum.Enum):
            t_field = enum.Enum

        if t_field not in type_to_form_fields:
            raise ValueError(f"Field {field_name} has unsupported type {field_info.annotation}")

        field_type = type_to_form_fields[t_field]
        match field_type:
            case forms.ChoiceField:
                choices = [(e.name, e.value) for e in t_field]
                declared_fields[field_name] = field_type(choices=choices)
            case _:
                declared_fields[field_name] = field_type()

    return type(f"{model.__name__}Form", (forms.Form,), declared_fields)
