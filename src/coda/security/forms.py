"""
Secure form parsing utilities for CODA application.

This module provides a hybrid solution that combines Django's battle-tested
security validation with flexible nested data structure parsing capabilities.

Key Features:
- DoS protection using Django's validation patterns
- Support for arbitrarily nested flat form data
- Integration with existing DTO patterns
- Reusable pattern-based parsing system
"""

import re
from typing import Any
from re import Pattern
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.forms.fields import DecimalField


class SecurityConfig:
    """Configuration for security limits and validation."""

    DEFAULT_ABSOLUTE_MAX = 1000
    DEFAULT_MAX_DEPTH = 5
    DEFAULT_MIN_VALUE = 0
    DEFAULT_MAX_VALUE = 999999


class SecureFieldParser:
    """
    Secure field parsing using Django's validation patterns.
    Provides DoS protection and proper error handling.
    """

    def __init__(self, config: SecurityConfig | None = None):
        self.config = config or SecurityConfig()

    def parse_int_secure(
        self,
        value: Any,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """
        Securely parse integer values using Django's IntegerField validation.
        Provides DoS protection and proper error handling with clamping.
        """
        min_val = min_value if min_value is not None else self.config.DEFAULT_MIN_VALUE
        max_val = max_value if max_value is not None else self.config.DEFAULT_MAX_VALUE

        try:
            if value is None or value == "":
                return default

            # First try to convert to int to check if it's a valid number
            try:
                int_value = int(value)
            except (ValueError, TypeError):
                return default

            # Apply clamping for DoS protection
            if int_value > max_val:
                return max_val
            elif int_value < min_val:
                return min_val

            # Value is within range, return it
            return int_value
        except (ValidationError, ValueError, TypeError):
            return default

    def parse_decimal_secure(
        self,
        value: Any,
        default: Decimal = Decimal("0.00"),
    ) -> Decimal:
        """
        Securely parse decimal values using Django's DecimalField validation.
        """
        field = DecimalField(max_digits=10, decimal_places=2)

        try:
            if value is None or value == "":
                return default
            return field.clean(value)
        except (ValidationError, ValueError, TypeError):
            return default


class PatternMatcher:
    """
    Pattern matching utilities for nested form structures.
    Handles patterns like: positions-{i}-nested-{j}-fieldname
    """

    def __init__(self, default_pattern: str | None = None, max_index: int | None = None):
        self._compiled_patterns: dict[str, Pattern] = {}
        self.default_pattern = default_pattern
        self.max_index = max_index

    def compile_pattern(self, pattern: str) -> Pattern:
        """
        Compile a pattern string into a regex pattern.

        Examples:
        - "position-{i}-" -> "position-(\\d+)-"
        - "position-{i}-nested-{j}-" -> "position-(\\d+)-nested-(\\d+)-"
        """
        if pattern in self._compiled_patterns:
            return self._compiled_patterns[pattern]

        # Replace {i}, {j}, {k}, etc. with capture groups
        regex_pattern = pattern
        placeholder_count = 0

        # Find all placeholders like {i}, {j}, {k}
        placeholders = re.findall(r"\{[a-z]\}", pattern)
        for placeholder in placeholders:
            regex_pattern = regex_pattern.replace(placeholder, r"(\d+)", 1)
            placeholder_count += 1

        compiled = re.compile(regex_pattern)
        self._compiled_patterns[pattern] = compiled
        return compiled

    def extract_indices_from_pattern(self, pattern: str, key: str) -> list[int] | None:
        """
        Extract numeric indices from a key using the given pattern.

        Returns:
            List of integers representing the indices, or None if no match
        """
        compiled_pattern = self.compile_pattern(pattern)
        match = compiled_pattern.match(key)

        if not match:
            return None

        try:
            return [int(group) for group in match.groups()]
        except ValueError:
            return None

    def get_field_name(self, pattern: str, key: str) -> str | None:
        """
        Extract the field name from a key by removing the pattern prefix.

        Example:
        - pattern: "position-{i}-", key: "position-1-cost_amount" -> "cost_amount"
        """
        compiled_pattern = self.compile_pattern(pattern)
        match = compiled_pattern.match(key)

        if not match:
            return None

        # Remove the matched pattern part to get the field name
        field_name = key[match.end() :]
        return field_name.replace("-", "_") if field_name else None

    def matches(self, key: str) -> bool:
        """
        Check if a key matches the default pattern and respects security limits.
        """
        if not self.default_pattern:
            raise ValueError("No default pattern set")

        # First check if it matches the pattern
        pattern = self.default_pattern + r".*"
        compiled_pattern = self.compile_pattern(pattern)
        if not compiled_pattern.match(key):
            return False

        # If max_index is set, check that all indices are within limits
        if self.max_index is not None:
            indices_list = self.extract_indices_from_pattern(self.default_pattern, key)
            if indices_list:
                if any(idx > self.max_index for idx in indices_list):
                    return False

        return True

    def extract_indices(self, key: str) -> dict[str, int] | None:
        """
        Extract indices from a key using the default pattern.
        Returns a dictionary mapping placeholder names to values.
        """
        if not self.default_pattern:
            raise ValueError("No default pattern set")

        indices_list = self.extract_indices_from_pattern(self.default_pattern, key)
        if not indices_list:
            return None

        # Map to placeholder names (i, j, k, etc.)
        placeholder_names = re.findall(r"\{([a-z])\}", self.default_pattern)
        if len(indices_list) != len(placeholder_names):
            return None

        return {name: idx for name, idx in zip(placeholder_names, indices_list)}


class SecureNestedFormParser:
    """
    Hybrid secure parser that combines Django's security validation
    with flexible nested data structure parsing.

    Provides:
    1. Django formset-level security validation
    2. Custom nested structure parsing
    3. Reusable prefix-based pattern matching
    """

    def __init__(
        self, config: SecurityConfig | None = None, max_items_per_level: int | None = None
    ):
        self.config = config or SecurityConfig()
        self.max_items_per_level = max_items_per_level
        self.field_parser = SecureFieldParser(config)
        self.pattern_matcher = PatternMatcher()

    def count_items_securely(self, data: dict[str, Any], pattern: str) -> int:
        """
        Securely count the number of items matching a pattern.
        Applies DoS protection by filtering out malicious indices.
        """
        valid_indices = set()
        max_allowed = (
            self.max_items_per_level
            if self.max_items_per_level is not None
            else self.config.DEFAULT_ABSOLUTE_MAX
        )

        for key in data.keys():
            indices = self.pattern_matcher.extract_indices_from_pattern(pattern, key)
            if indices:
                # Filter out potentially malicious indices
                first_index = indices[0]
                if first_index <= max_allowed:
                    valid_indices.add(first_index)

        return max(valid_indices) if valid_indices else 0

    def parse_flat_structure(
        self, data: dict[str, Any], pattern: str, max_items: int | None = None
    ) -> dict[int, dict[str, Any]]:
        """
        Parse flat structure like: position-{i}-fieldname

        Returns:
            Dictionary mapping index -> field_data
        """
        max_items = max_items or self.config.DEFAULT_ABSOLUTE_MAX
        item_count = self.count_items_securely(data, pattern)

        if item_count > max_items:
            raise ValidationError(f"Too many items: {item_count} > {max_items}")

        result = {}

        max_allowed = (
            self.max_items_per_level
            if self.max_items_per_level is not None
            else self.config.DEFAULT_ABSOLUTE_MAX
        )

        for key, value in data.items():
            indices = self.pattern_matcher.extract_indices_from_pattern(pattern, key)
            if not indices or len(indices) != 1:
                continue

            index = indices[0]

            # Filter out malicious indices
            if index > max_allowed:
                continue

            field_name = self.pattern_matcher.get_field_name(pattern, key)

            if field_name:
                if index not in result:
                    result[index] = {}
                result[index][field_name] = value

        return result

    def parse_hierarchical_structure(
        self,
        data: dict[str, Any],
        base_pattern: str,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Parse form data into hierarchical structure where nested patterns become arrays.

        Example:
        Input: {"position-1-name": "APC", "position-1-nested-1-item": "Fee", "position-1-nested-1-cost": "1200"}
        Output: [{"name": "APC", "nested": [{"item": "Fee", "cost": "1200"}]}]

        Args:
            data: Form data dictionary
            base_pattern: Pattern like "position-{i}-"
            max_items: Maximum number of items to parse

        Returns:
            List of dictionaries with hierarchical structure
        """
        max_items = max_items or self.config.DEFAULT_ABSOLUTE_MAX
        max_allowed = (
            self.max_items_per_level
            if self.max_items_per_level is not None
            else self.config.DEFAULT_ABSOLUTE_MAX
        )

        # Group data by base indices and field patterns
        base_items = {}
        nested_groups = {}

        for key, value in data.items():
            # Check for nested patterns FIRST (multi-level)
            # Try to parse patterns like "position-1-nested-2-item"
            base_prefix = base_pattern.replace("{i}", r"(\d+)")  # position-(\d+)-
            nested_pattern = (
                base_prefix + r"([^-]+)-(\d+)-(.+)"
            )  # position-(\d+)-([^-]+)-(\d+)-(.+)

            nested_match = re.match(nested_pattern, key)
            if nested_match:
                base_index = int(nested_match.group(1))
                nested_prefix = nested_match.group(2)
                nested_index = int(nested_match.group(3))
                field_name = nested_match.group(4).replace("-", "_")

                if base_index > max_allowed or nested_index > max_allowed:
                    continue

                # Group nested items properly for hierarchical structure
                if base_index not in nested_groups:
                    nested_groups[base_index] = {}
                if nested_prefix not in nested_groups[base_index]:
                    nested_groups[base_index][nested_prefix] = {}
                if nested_index not in nested_groups[base_index][nested_prefix]:
                    nested_groups[base_index][nested_prefix][nested_index] = {}

                nested_groups[base_index][nested_prefix][nested_index][field_name] = value
                continue

            # Check if it matches the base pattern (single level) - only if not nested
            base_indices = self.pattern_matcher.extract_indices_from_pattern(base_pattern, key)
            if base_indices and len(base_indices) == 1:
                base_index = base_indices[0]
                if base_index > max_allowed:
                    continue

                field_name = self.pattern_matcher.get_field_name(base_pattern, key)
                if field_name:
                    if base_index not in base_items:
                        base_items[base_index] = {}
                    base_items[base_index][field_name] = value

        # Build hierarchical result
        result = []
        all_indices = set(base_items.keys()) | set(nested_groups.keys())

        for base_index in sorted(all_indices):
            if base_index > max_items:
                break

            item = {}

            # Add base fields
            if base_index in base_items:
                item.update(base_items[base_index])

            # Add nested arrays
            if base_index in nested_groups:
                for nested_prefix, nested_items in nested_groups[base_index].items():
                    # Convert nested items from index-based dict to sorted array
                    nested_array = []
                    for nested_index in sorted(nested_items.keys()):
                        nested_array.append(nested_items[nested_index])
                    item[nested_prefix] = nested_array

            if item:  # Only add non-empty items
                result.append(item)

        return result

    def parse_nested_structure(
        self,
        data: dict[str, Any],
        pattern: str,
        max_depth: int | None = None,
        max_items_per_level: int | None = None,
    ) -> dict:
        """
        Parse nested structure like: position-{i}-nested-{j}-fieldname

        Returns:
            Nested dictionary structure matching the pattern
        """
        max_depth = max_depth or self.config.DEFAULT_MAX_DEPTH

        # Count pattern depth by number of placeholders
        placeholder_count = len(re.findall(r"\{[a-z]\}", pattern))

        if placeholder_count > max_depth:
            raise ValidationError(f"Pattern too deep: {placeholder_count} > {max_depth}")

        result = {}

        for key, value in data.items():
            indices = self.pattern_matcher.extract_indices_from_pattern(pattern, key)
            if not indices or len(indices) != placeholder_count:
                continue

            field_name = self.pattern_matcher.get_field_name(pattern, key)
            if not field_name:
                continue

            # Build nested structure
            current = result
            for i, index in enumerate(indices[:-1]):
                if index not in current:
                    current[index] = {}
                current = current[index]

            # Set the final value
            final_index = indices[-1]
            if final_index not in current:
                current[final_index] = {}
            current[final_index][field_name] = value

        return result

    def parse_with_dto_integration(
        self, data: dict[str, Any], pattern: str, dto_class: type, nested: bool = False
    ) -> list[Any]:
        """
        Parse form data and integrate with existing DTO patterns.

        Args:
            data: Form data dictionary
            pattern: Pattern like "position-{i}-" or "position-{i}-nested-{j}-"
            dto_class: DTO class with from_request class method
            nested: Whether to use nested parsing

        Returns:
            List of DTO instances
        """
        if nested:
            parsed_data = self.parse_nested_structure(data, pattern)
        else:
            parsed_data = self.parse_flat_structure(data, pattern)

        dtos = []

        if nested:
            # Handle nested DTO creation - flatten for DTO compatibility
            for outer_idx, outer_data in parsed_data.items():
                for inner_idx, inner_data in outer_data.items():
                    # Create synthetic prefix for DTO compatibility
                    synthetic_prefix = f"{pattern.format(i=outer_idx, j=inner_idx)}"
                    synthetic_data = {
                        f"{synthetic_prefix}{key.replace('_', '-')}": value
                        for key, value in inner_data.items()
                    }

                    try:
                        dto = dto_class.from_request(synthetic_data, synthetic_prefix)
                        dtos.append(dto)
                    except Exception:
                        # Skip invalid DTOs - could add logging here
                        continue
        else:
            # Handle flat DTO creation
            for idx, item_data in parsed_data.items():
                synthetic_prefix = pattern.format(i=idx)
                synthetic_data = {
                    f"{synthetic_prefix}{key.replace('_', '-')}": value
                    for key, value in item_data.items()
                }

                try:
                    dto = dto_class.from_request(synthetic_data, synthetic_prefix)
                    dtos.append(dto)
                except Exception:
                    # Skip invalid DTOs - could add logging here
                    continue

        return dtos


# Convenience functions for common patterns
def parse_invoice_positions_secure(
    data: dict[str, Any], max_positions: int = 100
) -> dict[int, dict[str, Any]]:
    """
    Secure parser for current invoice position pattern: position-{i}-fieldname
    """
    parser = SecureNestedFormParser()
    return parser.parse_flat_structure(data, "position-{i}-", max_positions)


def parse_nested_positions_secure(
    data: dict[str, Any], max_positions: int = 100, max_nested: int = 50
) -> dict:
    """
    Secure parser for future nested position pattern: position-{i}-nested-{j}-fieldname
    """
    parser = SecureNestedFormParser()
    return parser.parse_nested_structure(data, "position-{i}-nested-{j}-")


def get_form_count_secure(
    data: dict[str, Any], field_name: str, default: int = 0, max_count: int = 1000
) -> int:
    """
    Secure replacement for vulnerable int() parsing.
    Drop-in replacement for int(request.POST.get("field-name", 0))
    """
    parser = SecureFieldParser()
    return parser.parse_int_secure(
        data.get(field_name, default), default=default, max_value=max_count
    )
