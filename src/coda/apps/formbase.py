from collections.abc import Mapping
from typing import Any

from django import forms
from django.forms.renderers import BaseRenderer
from django.forms.utils import ErrorList


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
