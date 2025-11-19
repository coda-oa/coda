"""
Tests for Python 3.12 PEP 695 type alias syntax support.

PEP 695 introduces the new 'type' statement for type aliases:
    type MyAlias = str | int

This test suite verifies that the formdata package correctly handles
both old-style (TypeAlias) and new-style (PEP 695) type aliases.
"""

import datetime
from typing import TypeAlias

import pydantic

from coda import formdata

# ============================================================================
# PEP 695 Type Alias Definitions
# ============================================================================

type StringOrInt = str | int
type IntList = list[int]
type StringDict = dict[str, str]
type OptionalString = str | None


# ============================================================================
# Test Models Using PEP 695 Type Aliases
# ============================================================================


class SimpleData(pydantic.BaseModel):
    """Reusable model for nested tests."""

    a_str: str
    a_date: datetime.datetime


class DictData(pydantic.BaseModel):
    """Reusable model for dict tests."""

    a_dict: dict[str, str]


# Define PEP 695 type aliases for model unions (after models are defined)
type SimpleOrDict = SimpleData | DictData
type StringOrList = str | list[str]
type DictOrModel = dict[str, int] | SimpleData


class ModelWithSimpleAlias(pydantic.BaseModel):
    """Model using simple PEP 695 type alias."""

    value: StringOrInt


class ModelWithListAlias(pydantic.BaseModel):
    """Model using list type alias."""

    numbers: IntList


class ModelWithDictAlias(pydantic.BaseModel):
    """Model using dict type alias."""

    mapping: StringDict


class ModelWithOptionalAlias(pydantic.BaseModel):
    """Model using optional type alias."""

    optional_value: OptionalString = None


class ModelWithUnionAlias(pydantic.BaseModel):
    """Model using union of models type alias."""

    field: SimpleOrDict


class ModelWithComplexUnionAlias(pydantic.BaseModel):
    """Model with str | list[str] alias."""

    str_or_list: StringOrList


class ModelWithDictOrModelAlias(pydantic.BaseModel):
    """Model with dict | model alias."""

    dict_or_model: DictOrModel


# ============================================================================
# Simple Type Alias Tests
# ============================================================================


def test__pep695_simple_alias__maps_to_model() -> None:
    """Test that simple PEP 695 type aliases work."""
    expected = ModelWithSimpleAlias(value="test-string")

    actual = formdata.map_to_model(
        ModelWithSimpleAlias,
        {"value": "test-string"},
    )

    assert actual == expected


def test__pep695_simple_alias__with_int__maps_to_model() -> None:
    """Test that PEP 695 type aliases work with int values."""
    # Note: When Pydantic receives "42" as a string with a str | int union,
    # it keeps it as a string since that's a valid member of the union.
    # This is expected behavior.
    expected = ModelWithSimpleAlias(value="42")

    actual = formdata.map_to_model(
        ModelWithSimpleAlias,
        {"value": "42"},
    )

    assert actual == expected


# ============================================================================
# List Type Alias Tests
# ============================================================================


def test__pep695_list_alias__list_in_dict__maps_to_model() -> None:
    """Test PEP 695 list alias with list already in dict."""
    expected = ModelWithListAlias(numbers=[1, 2, 3])

    actual = formdata.map_to_model(
        ModelWithListAlias,
        {"numbers": ["1", "2", "3"]},
    )

    assert actual == expected


def test__pep695_list_alias__list_in_flat_form__maps_to_model() -> None:
    """Test PEP 695 list alias with flattened form data."""
    expected = ModelWithListAlias(numbers=[1, 2, 3])

    actual = formdata.map_to_model(
        ModelWithListAlias,
        {
            "#-numbers": "3",
            "numbers-1": "1",
            "numbers-2": "2",
            "numbers-3": "3",
        },
    )

    assert actual == expected


def test__pep695_list_alias__empty_list__maps_to_model() -> None:
    """Test PEP 695 list alias with empty list."""
    expected = ModelWithListAlias(numbers=[])

    actual = formdata.map_to_model(
        ModelWithListAlias,
        {"#-numbers": "0"},
    )

    assert actual == expected


# ============================================================================
# Dict Type Alias Tests
# ============================================================================


def test__pep695_dict_alias__maps_to_model() -> None:
    """Test PEP 695 dict alias with prefixed keys."""
    expected = ModelWithDictAlias(mapping={"key1": "value1", "key2": "value2"})

    actual = formdata.map_to_model(
        ModelWithDictAlias,
        {
            "mapping-key1": "value1",
            "mapping-key2": "value2",
        },
    )

    assert actual == expected


def test__pep695_dict_alias__empty_dict__maps_to_model() -> None:
    """Test PEP 695 dict alias with no matching keys."""
    expected = ModelWithDictAlias(mapping={})

    actual = formdata.map_to_model(
        ModelWithDictAlias,
        {"other_key": "value"},
    )

    assert actual == expected


# ============================================================================
# Optional Type Alias Tests
# ============================================================================


def test__pep695_optional_alias__with_value__maps_to_model() -> None:
    """Test PEP 695 optional alias with value present."""
    expected = ModelWithOptionalAlias(optional_value="present")

    actual = formdata.map_to_model(
        ModelWithOptionalAlias,
        {"optional_value": "present"},
    )

    assert actual == expected


def test__pep695_optional_alias__with_none__maps_to_model() -> None:
    """Test PEP 695 optional alias with value absent."""
    expected = ModelWithOptionalAlias(optional_value=None)

    actual = formdata.map_to_model(
        ModelWithOptionalAlias,
        {},
    )

    assert actual == expected


# ============================================================================
# Union of Models Type Alias Tests
# ============================================================================


def test__pep695_model_union_alias__simple_model__maps_correctly() -> None:
    """Test PEP 695 union alias resolves to SimpleData model."""
    now = datetime.datetime.now()
    expected = ModelWithUnionAlias(field=SimpleData(a_str="test-value", a_date=now))

    actual = formdata.map_to_model(
        ModelWithUnionAlias,
        {
            "field-a_str": "test-value",
            "field-a_date": now.isoformat(),
        },
    )

    assert actual == expected


def test__pep695_model_union_alias__dict_model__maps_correctly() -> None:
    """Test PEP 695 union alias resolves to DictData model."""
    expected = ModelWithUnionAlias(field=DictData(a_dict={"key1": "val1", "key2": "val2"}))

    actual = formdata.map_to_model(
        ModelWithUnionAlias,
        {
            "field-a_dict-key1": "val1",
            "field-a_dict-key2": "val2",
        },
    )

    assert actual == expected


# ============================================================================
# Complex Union Type Alias Tests
# ============================================================================


def test__pep695_str_or_list_alias__with_str__maps_to_model() -> None:
    """Test PEP 695 str | list[str] alias with string value."""
    expected = ModelWithComplexUnionAlias(str_or_list="simple-string")

    actual = formdata.map_to_model(
        ModelWithComplexUnionAlias,
        {"str_or_list": "simple-string"},
    )

    assert actual == expected


def test__pep695_str_or_list_alias__with_list__maps_to_model() -> None:
    """Test PEP 695 str | list[str] alias with list value."""
    expected = ModelWithComplexUnionAlias(str_or_list=["a", "b", "c"])

    actual = formdata.map_to_model(
        ModelWithComplexUnionAlias,
        {
            "#-str_or_list": "3",
            "str_or_list-1": "a",
            "str_or_list-2": "b",
            "str_or_list-3": "c",
        },
    )

    assert actual == expected


def test__pep695_dict_or_model_alias__with_dict__maps_to_model() -> None:
    """Test PEP 695 dict | model alias resolves to dict."""
    expected = ModelWithDictOrModelAlias(dict_or_model={"key1": 10, "key2": 20})

    actual = formdata.map_to_model(
        ModelWithDictOrModelAlias,
        {
            "dict_or_model-key1": "10",
            "dict_or_model-key2": "20",
        },
    )

    assert actual == expected


def test__pep695_dict_or_model_alias__with_model__maps_to_model() -> None:
    """Test PEP 695 dict | model alias resolves to model."""
    now = datetime.datetime.now()
    expected = ModelWithDictOrModelAlias(dict_or_model=SimpleData(a_str="test", a_date=now))

    actual = formdata.map_to_model(
        ModelWithDictOrModelAlias,
        {
            "dict_or_model-a_str": "test",
            "dict_or_model-a_date": now.isoformat(),
        },
    )

    assert actual == expected


# ============================================================================
# Nested Models with PEP 695 Type Aliases
# ============================================================================


class ParentWithAliasField(pydantic.BaseModel):
    """Model with nested field using PEP 695 alias."""

    parent_value: str
    nested: SimpleOrDict


def test__pep695_nested_model_with_alias__maps_correctly() -> None:
    """Test nested model using PEP 695 type alias."""
    now = datetime.datetime.now()
    expected = ParentWithAliasField(
        parent_value="parent",
        nested=SimpleData(a_str="nested", a_date=now),
    )

    actual = formdata.map_to_model(
        ParentWithAliasField,
        {
            "parent_value": "parent",
            "nested-a_str": "nested",
            "nested-a_date": now.isoformat(),
        },
    )

    assert actual == expected


# ============================================================================
# List of Models with PEP 695 Type Aliases
# ============================================================================

type SimpleDataList = list[SimpleData]


class ModelWithListOfModelsAlias(pydantic.BaseModel):
    """Model with list of models using PEP 695 alias."""

    items: SimpleDataList


def test__pep695_list_of_models_alias__maps_correctly() -> None:
    """Test list of models using PEP 695 type alias."""
    now = datetime.datetime.now()
    expected = ModelWithListOfModelsAlias(
        items=[
            SimpleData(a_str="first", a_date=now),
            SimpleData(a_str="second", a_date=now),
        ]
    )

    actual = formdata.map_to_model(
        ModelWithListOfModelsAlias,
        {
            "#-items": "2",
            "items-1-a_str": "first",
            "items-1-a_date": now.isoformat(),
            "items-2-a_str": "second",
            "items-2-a_date": now.isoformat(),
        },
    )

    assert actual == expected


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


type ComplexNestedAlias = list[StringOrInt]


class ModelWithNestedAlias(pydantic.BaseModel):
    """Model with nested type aliases."""

    values: ComplexNestedAlias


def test__pep695_nested_type_alias__maps_correctly() -> None:
    """Test nested PEP 695 type aliases (list of union)."""
    # Note: When Pydantic receives "42" as a string with a str | int union,
    # it keeps it as a string since that's a valid member of the union.
    expected = ModelWithNestedAlias(values=["string", "42", "another"])

    actual = formdata.map_to_model(
        ModelWithNestedAlias,
        {
            "#-values": "3",
            "values-1": "string",
            "values-2": "42",
            "values-3": "another",
        },
    )

    assert actual == expected


# ============================================================================
# Comparison Tests: Old vs New Syntax
# ============================================================================


OldStyleAlias: TypeAlias = str | int


class ModelWithOldStyleAlias(pydantic.BaseModel):
    """Model using old-style TypeAlias for comparison."""

    value: OldStyleAlias


def test__old_style_type_alias__still_works() -> None:
    """Verify old-style TypeAlias continues to work."""
    expected = ModelWithOldStyleAlias(value="test")

    actual = formdata.map_to_model(
        ModelWithOldStyleAlias,
        {"value": "test"},
    )

    assert actual == expected


def test__both_alias_styles__behave_identically() -> None:
    """Verify old and new style aliases produce identical results."""
    old_result = formdata.map_to_model(
        ModelWithOldStyleAlias,
        {"value": "42"},
    )

    new_result = formdata.map_to_model(
        ModelWithSimpleAlias,
        {"value": "42"},
    )

    assert old_result.value == new_result.value
