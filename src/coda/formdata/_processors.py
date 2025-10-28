from abc import ABC, abstractmethod
from typing import Any, get_args

import pydantic
from pydantic.fields import FieldInfo

from ._annotations import (
    get_all_model_types,
    get_matching_model_type,
    is_dict,
    is_pydantic_model,
    is_sequence_field,
    is_union,
)
from ._errors import CannotProcessField, FieldAlreadyExists, ValidationFailed
from ._keys import KeyMatcher
from ._mapper import map_to_model


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

    def __init__(self, max_sequence_length: int) -> None:
        super().__init__()
        self.model_processor = ModelFieldProcessor()
        self.max_sequence_length = max_sequence_length

    def can_handle_field(
        self, data: dict[str, Any], field_name: str, field_info: FieldInfo
    ) -> bool:
        """
        Determines handling capability by analyzing both type AND data patterns.

        Checks for:
        1. Sequence type annotation (list, tuple, etc.)
        2. Sequence counter pattern in data (field-# key exists)
        """
        if not (field_info.annotation and is_sequence_field(field_info.annotation)):
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

        if number_of_fields > self.max_sequence_length:
            raise ValidationFailed(
                f"Sequence too large for field '{field_name}': {number_of_fields} > {self.max_sequence_length}"
            )

        annotation = field_info.annotation
        annotation_args = get_args(annotation)
        has_pydantic_models = any(is_pydantic_model(arg) for arg in annotation_args)

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

        if is_union(field_info.annotation):
            return self._analyze_union_data_patterns(field_info)

        return is_pydantic_model(field_info.annotation)

    def _analyze_union_data_patterns(self, field_info: FieldInfo) -> bool:
        """
        Quick structural check for union types - can potentially handle if there's a model in the union.
        """
        if is_union(field_info.annotation):
            return any(is_pydantic_model(arg) for arg in get_args(field_info.annotation))

        return is_pydantic_model(field_info.annotation)

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
        possible_models = get_all_model_types(annotation)
        if not possible_models:
            return None

        nested_data = self.key_matcher.get_keys_with_prefix(data, field_key)
        if not nested_data:
            return None

        nested_prefix = field_key + self.key_matcher.separator
        model_type = get_matching_model_type(possible_models, nested_data, nested_prefix)

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

        if is_union(field_info.annotation):
            return any(is_dict(arg) for arg in get_args(field_info.annotation))

        return is_dict(field_info.annotation)

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

        if not is_union(field_info.annotation):
            if is_dict(field_info.annotation):
                return result_dict
            else:
                raise CannotProcessField(f"Field '{field_name}' is not a dict type")

        for union_arg in get_args(field_info.annotation):
            if is_dict(union_arg):
                return result_dict

        raise CannotProcessField(f"No dict type found in union for field '{field_name}'")
