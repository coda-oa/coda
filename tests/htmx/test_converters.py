from typing import NamedTuple

from coda.apps.htmx_components.converters import to_htmx_formset_data


def test__list_of_dicts__converts_to_dict_with_form_prefixes() -> None:
    data = [
        {"field": "field-1"},
        {"field": "field-2"},
        {"field": "field-3"},
    ]

    form_data = to_htmx_formset_data(data, prefix="prefix")
    assert form_data == {
        "prefix-total_forms": ["3"],
        "prefix-form-1-field": ["field-1"],
        "prefix-form-2-field": ["field-2"],
        "prefix-form-3-field": ["field-3"],
    }


def test__list_of_objects__converts_to_dict_with_form_prefixes() -> None:
    class FormData:
        def __init__(self, field: str) -> None:
            self.field = field

        def some_method(self) -> None:
            pass

    data = [
        FormData("field-1"),
        FormData("field-2"),
        FormData("field-3"),
    ]

    form_data = to_htmx_formset_data(data, prefix="prefix")
    assert form_data == {
        "prefix-total_forms": ["3"],
        "prefix-form-1-field": ["field-1"],
        "prefix-form-2-field": ["field-2"],
        "prefix-form-3-field": ["field-3"],
    }


def test__list_of_named_tuples__converts_to_dict_with_form_prefixes() -> None:
    class FormData(NamedTuple):
        field: str

    data = [
        FormData("field-1"),
        FormData("field-2"),
        FormData("field-3"),
    ]

    form_data = to_htmx_formset_data(data, prefix="prefix")
    assert form_data == {
        "prefix-total_forms": ["3"],
        "prefix-form-1-field": ["field-1"],
        "prefix-form-2-field": ["field-2"],
        "prefix-form-3-field": ["field-3"],
    }


def test__list_of_dataclasses__converts_to_dict_with_form_prefixes() -> None:
    from dataclasses import dataclass

    @dataclass
    class FormData:
        field: str

    data = [
        FormData("field-1"),
        FormData("field-2"),
        FormData("field-3"),
    ]

    form_data = to_htmx_formset_data(data, prefix="prefix")
    assert form_data == {
        "prefix-total_forms": ["3"],
        "prefix-form-1-field": ["field-1"],
        "prefix-form-2-field": ["field-2"],
        "prefix-form-3-field": ["field-3"],
    }
