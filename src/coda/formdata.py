import types
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, Union, get_args, get_origin

import pydantic
from pydantic.fields import FieldInfo

M = TypeVar("M", bound=pydantic.BaseModel)

DEFAULT_FIELD_SEPARATOR = "-"
SEQUENCE_COUNTER_PREFIX = "#"
_SEQUENCE_LENGTH = f"{SEQUENCE_COUNTER_PREFIX}{DEFAULT_FIELD_SEPARATOR}{{field_name}}"

MAX_SEQUENCE_LENGTH = 10000
MAX_RECURSION_DEPTH = 50


class CannotProcessField(Exception):
    """Base exception raised when a processor cannot handle a field."""

    pass


class FieldAlreadyExists(CannotProcessField):
    """Raised when a field already exists in the data."""

    pass


class ValidationFailed(Exception):
    """Raised when field validation fails during processing."""

    pass


class KeyMatcher:
    """Utility class for handling key matching and prefix operations in form data."""

    def __init__(self, separator: str = DEFAULT_FIELD_SEPARATOR):
        self.separator = separator

    def strip_prefix(self, data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """Remove prefix from all keys in data and return new dict."""
        if not prefix:
            return data.copy()

        strip = prefix + self.separator
        return {k.removeprefix(strip): v for k, v in data.items()}

    def get_keys_with_prefix(self, data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """Get all key-value pairs where key starts with prefix."""
        prefix_with_separator = prefix + self.separator
        return {k: v for k, v in data.items() if k.startswith(prefix_with_separator)}

    def build_sequence_key(self, field_name: str, index: int) -> str:
        """Build key for sequence item: field_name-index."""
        return f"{field_name}{self.separator}{index}"

    def build_counter_key(self, field_name: str) -> str:
        """Build counter key: #-field_name."""
        return _SEQUENCE_LENGTH.format(field_name=field_name)

    def matches_field_pattern(self, key: str, field_name: str) -> bool:
        """Check if key matches field pattern (exact match or starts with field_name-)."""
        return (
            key == field_name
            or key.startswith(field_name + self.separator)
            or key == self.build_counter_key(field_name)
        )


def with_union_support(type_checker_func: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """Decorator to automatically handle union types in type checkers."""

    def wrapper(annotation: Any) -> bool:
        if _is_union(annotation):
            return any(type_checker_func(arg) for arg in get_args(annotation))
        return type_checker_func(annotation)

    return wrapper


class FieldProcessor(ABC):
    """Abstract base class for processing different types of form fields."""

    def __init__(self) -> None:
        self.key_matcher = KeyMatcher()

    @abstractmethod
    def can_handle_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo
    ) -> bool:
        """
        STRUCTURAL CHECK ONLY - fast type/pattern analysis.

        Should answer: "Could this processor theoretically handle this field type?"
        - Check type annotations
        - Check for required data patterns (prefixed keys, etc.)
        - NO actual processing or validation
        - Should be fast and deterministic
        """
        pass

    @abstractmethod
    def try_process_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo, **kwargs: Any
    ) -> Any:
        """
        Pure function that processes field data without side effects.

        Args:
            data: Input data dictionary (read-only)
            field_name: Name of the field to process
            field_info: Pydantic field information
            **kwargs: Additional processing context (e.g., model)

        Returns:
            Any: The parsed result (model instance, list, dict, etc.)

        Raises:
            CannotProcessField: If this processor cannot handle the field
            FieldAlreadyExists: If field already exists (should skip)
            ValidationFailed: If processing/validation fails
        """
        pass

    def _should_skip_field(self, data: dict[str, Any], field_name: str) -> bool:
        """Check if field processing should be skipped (field already exists in data)."""
        return field_name in data


class ProcessorChain:
    """Chain of Responsibility implementation for field processing."""

    def __init__(self, processors: list[FieldProcessor]):
        self.processors = processors

    def process_field(
        self, input_data: dict[str, Any], field_name: str, field_info: FieldInfo, **kwargs: Any
    ) -> Any:
        """
        Try processors until one succeeds, return parsed result.

        Args:
            input_data: Input data dictionary (read-only)
            field_name: Name of the field to process
            field_info: Field information
            **kwargs: Additional processor-specific arguments

        Returns:
            Any: The parsed result from the successful processor

        Raises:
            CannotProcessField: If no processor can handle the field
        """
        for processor in self.processors:
            if processor.can_handle_field(input_data, field_name, field_info):
                try:
                    return processor.try_process_field(input_data, field_name, field_info, **kwargs)
                except CannotProcessField:
                    continue

        raise CannotProcessField(f"No processor could handle field '{field_name}'")

    def process_all_fields(
        self, input_data: dict[str, Any], fields: dict[str, FieldInfo], **kwargs: Any
    ) -> dict[str, Any]:
        """
        Args:
            input_data: Input data dictionary (read-only)
            fields: Field definitions from pydantic model
            **kwargs: Additional processor-specific arguments

        Returns:
            dict[str, Any]: Clean output dictionary with processed field values
        """
        output_data = {}

        for field_name, field_info in fields.items():
            try:
                result = self.process_field(input_data, field_name, field_info, **kwargs)
                output_data[field_name] = result
            except CannotProcessField:
                if field_name in input_data:
                    output_data[field_name] = input_data[field_name]

        return output_data


class SequenceFieldProcessor(FieldProcessor):
    """Processor for sequence fields (lists, tuples, etc.)."""

    def __init__(self) -> None:
        super().__init__()
        self.model_processor = ModelFieldProcessor()

    def can_handle_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo
    ) -> bool:
        """
        Determines handling capability by analyzing both type AND data patterns.

        Checks for:
        1. Sequence type annotation (list, tuple, etc.)
        2. Sequence counter pattern in data (field-# key exists)
        """
        if not (field_info.annotation and _is_sequence_field(field_info.annotation)):
            return False

        counter_key = self.key_matcher.build_counter_key(field_name)
        return counter_key in data

    def try_process_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo, **kwargs: Any
    ) -> Any:
        """
        Args:
            data: Input data dictionary (read-only)
            field_name: Name of the field to process
            field_info: Pydantic field information
            **kwargs: Additional processing context (must include 'model')

        Returns:
            list: The parsed sequence values

        Raises:
            CannotProcessField: If this processor cannot handle the field
            FieldAlreadyExists: If field already exists (should skip)
            ValidationFailed: If processing/validation fails
        """
        if self._should_skip_field(data, field_name):
            raise FieldAlreadyExists(f"Field '{field_name}' already exists in data")

        model = kwargs.get("model")
        if not model:
            raise CannotProcessField("Model not provided in kwargs")

        counter_key = self.key_matcher.build_counter_key(field_name)
        if counter_key not in data:
            raise CannotProcessField(f"No sequence counter found for field '{field_name}'")

        try:
            number_of_fields = int(data[counter_key])
        except (ValueError, TypeError) as e:
            raise ValidationFailed(f"Invalid sequence counter for field '{field_name}': {e}") from e

        if number_of_fields < 0:
            raise ValidationFailed(
                f"Sequence counter cannot be negative for field '{field_name}': {number_of_fields}"
            )

        if number_of_fields > MAX_SEQUENCE_LENGTH:
            raise ValidationFailed(
                f"Sequence too large for field '{field_name}': {number_of_fields} > {MAX_SEQUENCE_LENGTH}"
            )

        annotation = field_info.annotation
        annotation_args = get_args(annotation)
        has_pydantic_models = any(_is_pydantic_model(arg) for arg in annotation_args)

        field_values = []
        for i in range(1, number_of_fields + 1):
            field_key = self.key_matcher.build_sequence_key(field_name, i)

            if field_key in data:
                field_values.append(data[field_key])
            elif has_pydantic_models:
                model_annotation = annotation_args[0]
                try:
                    model_instance = self.model_processor.process_model_field(
                        data, field_key, model_annotation
                    )
                    if model_instance is not None:
                        field_values.append(model_instance)
                    else:
                        raise ValidationFailed(
                            f"Failed to process model at index {i} for field '{field_name}'"
                        )
                except Exception as e:
                    raise ValidationFailed(
                        f"Failed to process sequence item {i} for field '{field_name}': {e}"
                    ) from e

        return field_values


class ModelFieldProcessor(FieldProcessor):
    """Processor for model fields (nested Pydantic models)."""

    def can_handle_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo
    ) -> bool:
        """
        Determines handling by analyzing type annotations AND data patterns.

        For union types (e.g., dict[str, int] | SomeModel), analyzes actual
        data structure to determine if it represents a model or simple mapping.
        """
        if not field_info.annotation:
            return False

        prefixed_keys = self.key_matcher.get_keys_with_prefix(data, field_name)
        if not prefixed_keys:
            return False

        if _is_union(field_info.annotation):
            return self._analyze_union_data_patterns(field_info)

        return _is_pydantic_model(field_info.annotation)

    def _analyze_union_data_patterns(self, field_info: FieldInfo) -> bool:
        """
        Quick structural check for union types - can potentially handle if there's a model in the union.
        """
        if _is_union(field_info.annotation):
            return any(_is_pydantic_model(arg) for arg in get_args(field_info.annotation))

        return _is_pydantic_model(field_info.annotation)

    def process_model_field(
        self, data: dict[str, Any], field_key: str, annotation: Any
    ) -> pydantic.BaseModel | None:
        """
        Process a single model field - reusable by other processors.

        Args:
            data: The form data containing the field
            field_key: The key/prefix for this field in the data
            annotation: The type annotation for this field

        Returns:
            Model instance if successfully processed, None otherwise
        """
        possible_models = _get_all_model_types(annotation)
        if not possible_models:
            return None

        nested_data = self.key_matcher.get_keys_with_prefix(data, field_key)
        if not nested_data:
            return None

        nested_prefix = field_key + self.key_matcher.separator
        model_type = _get_matching_model_type(possible_models, nested_data, nested_prefix)

        if not model_type:
            return None

        try:
            return map_to_model(model_type, nested_data, prefix=field_key)
        except pydantic.ValidationError:
            return None

    def try_process_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo, **kwargs: Any
    ) -> Any:
        """
        Args:
            data: Input data dictionary (read-only)
            field_name: Name of the field to process
            field_info: Pydantic field information
            **kwargs: Additional processing context

        Returns:
            pydantic.BaseModel: The parsed model instance

        Raises:
            CannotProcessField: If this processor cannot handle the field
            FieldAlreadyExists: If field already exists (should skip)
            ValidationFailed: If processing/validation fails
        """
        if self._should_skip_field(data, field_name):
            raise FieldAlreadyExists(f"Field '{field_name}' already exists in data")

        try:
            model_instance = self.process_model_field(data, field_name, field_info.annotation)
            if model_instance is None:
                raise CannotProcessField(f"Could not process model field '{field_name}'")
            return model_instance
        except pydantic.ValidationError as e:
            raise ValidationFailed(f"Model validation failed for field '{field_name}': {e}") from e
        except Exception as e:
            raise CannotProcessField(f"Failed to process model field '{field_name}': {e}") from e


class MappingFieldProcessor(FieldProcessor):
    """Processor for mapping fields (dict fields)."""

    def can_handle_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo
    ) -> bool:
        """
        Structural check - can potentially handle dict types.

        Does NOT assume anything about what other processors have done.
        The actual decision is made in try_process_field() through validation.
        """
        if not field_info.annotation:
            return False

        if _is_union(field_info.annotation):
            return any(_is_dict(arg) for arg in get_args(field_info.annotation))

        return _is_dict(field_info.annotation)

    def try_process_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo, **kwargs: Any
    ) -> Any:
        """
        Args:
            data: Input data dictionary (read-only)
            field_name: Name of the field to process
            field_info: Pydantic field information
            **kwargs: Additional processing context

        Returns:
            dict: The parsed dictionary with prefixes stripped

        Raises:
            CannotProcessField: If this processor cannot handle the field
            FieldAlreadyExists: If field already exists (should skip)
            ValidationFailed: If processing/validation fails
        """
        if self._should_skip_field(data, field_name):
            raise FieldAlreadyExists(f"Field '{field_name}' already exists in data")

        mapping_data = self.key_matcher.get_keys_with_prefix(data, field_name)

        result_dict = {}
        if mapping_data:
            mapping_prefix = field_name + self.key_matcher.separator
            for k, v in mapping_data.items():
                new_key = k.removeprefix(mapping_prefix)
                result_dict[new_key] = v

        if not _is_union(field_info.annotation):
            if _is_dict(field_info.annotation):
                return result_dict
            else:
                raise CannotProcessField(f"Field '{field_name}' is not a dict type")

        for union_arg in get_args(field_info.annotation):
            if _is_dict(union_arg):
                return result_dict

        raise CannotProcessField(f"No dict type found in union for field '{field_name}'")


def map_to_model(model: type[M], data: dict[str, Any], prefix: str = "") -> M:
    key_matcher = KeyMatcher()
    input_data = key_matcher.strip_prefix(data, prefix)

    processor_chain = ProcessorChain(
        [
            SequenceFieldProcessor(),
            ModelFieldProcessor(),
            MappingFieldProcessor(),
        ]
    )

    processed_data = processor_chain.process_all_fields(input_data, model.model_fields, model=model)

    return model(**processed_data)


@with_union_support
def _is_dict(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation
    try:
        return origin is dict or issubclass(origin, Mapping)
    except TypeError:
        return False


@with_union_support
def _is_sequence_field(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation

    if origin in (list, tuple):
        return True

    try:
        return issubclass(origin, Sequence) and origin is not str
    except TypeError:
        return False


@with_union_support
def _is_pydantic_model(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation
    try:
        return issubclass(origin, pydantic.BaseModel)
    except TypeError:
        return False


def _is_union(annotation: Any) -> bool:
    return get_origin(annotation) in (Union, getattr(types, "UnionType", None))


def _get_matching_model_type(
    candidates: list[type[pydantic.BaseModel]], data: dict[str, Any], prefix: str
) -> type[pydantic.BaseModel] | None:
    for c in candidates:
        if _keys_match_model_fields(c, data, prefix):
            return c

    return None


def _keys_match_model_fields(
    model: type[pydantic.BaseModel], data: dict[str, Any], prefix: str
) -> bool:
    """Check if data keys match the model's field structure after prefix removal."""
    key_matcher = KeyMatcher()
    model_fields = model.model_fields

    for key in data.keys():
        stripped = key.removeprefix(prefix)

        matched = False
        for field_name in model_fields.keys():
            if key_matcher.matches_field_pattern(stripped, field_name):
                matched = True
                break

        if not matched:
            return False

    return True


def _get_all_model_types(annotation: Any) -> list[type[pydantic.BaseModel]]:
    """Extract all Pydantic model types from an annotation (including unions)."""
    if _is_union(annotation):
        models: list[type[pydantic.BaseModel]] = []
        for arg in get_args(annotation):
            models.extend(_get_all_model_types(arg))
        return models

    try:
        if issubclass(annotation, pydantic.BaseModel):
            return [annotation]
    except TypeError:
        pass

    return []
