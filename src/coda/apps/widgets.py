from collections.abc import Iterator, Mapping
from datetime import date
from typing import Any, cast

from django import forms

from coda.domain.date import DateRange


class DateRangeWidget(forms.MultiWidget):
    def __init__(self, *, input_names: tuple[str, str], input_ids: tuple[str, str]) -> None:
        self.input_names = input_names
        self.input_ids = input_ids
        super().__init__(
            [
                forms.DateInput(attrs={"type": "date"}),
                forms.DateInput(attrs={"type": "date"}),
            ]
        )

    def get_context(self, name: str, value: Any, attrs: Any) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        for index, subwidget in enumerate(context["widget"]["subwidgets"]):
            subwidget["name"] = self._input_name(name, index)
            subwidget["attrs"]["id"] = self.input_ids[index]
        return context

    def subwidgets(self, name: str, value: Any, attrs: Any = None) -> Iterator[dict[str, Any]]:
        context = self.get_context(name, value, attrs)
        subwidgets = cast(list[dict[str, Any]], context["widget"]["subwidgets"])
        return iter(subwidgets)

    def value_from_datadict(self, data: Any, files: Any, name: str) -> list[Any]:
        return [
            widget.value_from_datadict(data, files, self._input_name(name, index))
            for index, widget in enumerate(self.widgets)
        ]

    def value_omitted_from_data(self, data: Any, files: Any, name: str) -> bool:
        return all(
            widget.value_omitted_from_data(data, files, self._input_name(name, index))
            for index, widget in enumerate(self.widgets)
        )

    def decompress(self, value: Any) -> list[Any]:
        if value is None:
            return ["", ""]
        if isinstance(value, DateRange):
            return [
                "" if value.start == date.min else value.start.isoformat(),
                "" if value.end == date.max else value.end.isoformat(),
            ]
        return list(value) if isinstance(value, (list, tuple)) else ["", ""]

    def mark_invalid(self) -> None:
        self.attrs.update({"aria-invalid": "true", "aria-describedby": "date-range-error"})

    def _input_name(self, field_name: str, index: int) -> str:
        prefix, separator, _ = field_name.rpartition("-")
        name = self.input_names[index]
        return f"{prefix}-{name}" if separator else name


class SearchSelectWidget(forms.Select):
    template_name = "forms/search-select-widget.html"
    option_template_name = "forms/search-select-option-widget.html"


class SearchSelectMultiWidget(forms.SelectMultiple):
    template_name = "forms/search-select-multi-widget.html"
    option_template_name = "forms/search-select-multi-option-widget.html"

    option_attrs: Mapping[str, Mapping[str, str]]

    def create_option(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        option = super().create_option(*args, **kwargs)
        value = args[1] if len(args) > 1 else kwargs["value"]
        extra_attrs = getattr(self, "option_attrs", {}).get(str(value))
        if extra_attrs:
            option["attrs"].update(extra_attrs)
        return option


class PublicationTypeRadioSelect(forms.RadioSelect):
    def create_option(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        option = super().create_option(*args, **kwargs)
        value = args[1] if len(args) > 1 else kwargs["value"]
        option["attrs"]["id"] = f"publication_type_{value}"
        return option


class SwitchInput(forms.CheckboxInput):
    def get_context(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context(*args, **kwargs)
        context["widget"]["attrs"]["aria-checked"] = (
            "true" if context["widget"]["attrs"].get("checked") else "false"
        )
        return context
