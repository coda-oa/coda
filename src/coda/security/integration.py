"""
Integration helpers for the SecureNestedFormParser.

This module provides utilities to integrate the secure parser
with the existing CODA codebase, particularly the DTO patterns.
"""

from typing import Any
from django.http import HttpRequest


class SecureFormIntegration:
    """
    Integration helpers for using SecureNestedFormParser with existing code.
    """

    @staticmethod
    def secure_position_count(request: HttpRequest, max_positions: int = 100) -> int:
        """
        Secure replacement for:
        number_of_positions = int(request.POST.get("number-of-positions", 0))

        This is a drop-in replacement that should be used in:
        - /app/src/coda/apps/invoices/views/position_list.py:77
        - /app/src/coda/apps/invoices/views/create.py:65
        """
        from django.forms.fields import IntegerField
        from django.core.exceptions import ValidationError

        field = IntegerField(min_value=0)

        try:
            raw_value = request.POST.get("number-of-positions", 0)
            if raw_value is None or raw_value == "":
                return 0

            # Clean the value first
            clean_value = field.clean(raw_value)

            # Apply max limit manually (clamp to max instead of rejecting)
            return min(clean_value, max_positions)

        except (ValidationError, ValueError, TypeError):
            return 0

    @staticmethod
    def secure_total_forms(
        data: dict[str, Any], prefix: str, min_forms: int = 1, max_forms: int = 50
    ) -> int:
        """
        Secure replacement for:
        int(data.get(prefix + "total_forms", min_forms))

        This should be used in:
        - /app/src/coda/apps/htmx_components/forms.py:24
        """
        from django.forms.fields import IntegerField
        from django.core.exceptions import ValidationError

        field = IntegerField(min_value=0)

        try:
            raw_value = data.get(prefix + "total_forms", min_forms)
            if raw_value is None or raw_value == "":
                return min_forms

            # Clean the value first
            clean_value = field.clean(raw_value)

            # Apply max limit manually (clamp to max instead of rejecting)
            return min(clean_value, max_forms)

        except (ValidationError, ValueError, TypeError):
            return min_forms

    @staticmethod
    def secure_form_index(form_index_str: str, max_index: int = 50) -> int:
        """
        Secure replacement for:
        int(_form_index)

        This should be used in:
        - /app/src/coda/apps/htmx_components/forms.py:283
        """
        from django.forms.fields import IntegerField
        from django.core.exceptions import ValidationError

        field = IntegerField(min_value=0)

        try:
            if form_index_str is None or form_index_str == "":
                return 0

            # Clean the value first
            clean_value = field.clean(form_index_str)

            # Apply max limit manually (clamp to max instead of rejecting)
            return min(clean_value, max_index)

        except (ValidationError, ValueError, TypeError):
            return 0

    @staticmethod
    def secure_wizard_step(store_data: dict[str, Any], max_steps: int = 20) -> int:
        """
        Secure replacement for:
        int(self.get_store().get("step", 0))

        This should be used in:
        - /app/src/coda/apps/wizard.py:190
        """
        from django.forms.fields import IntegerField
        from django.core.exceptions import ValidationError

        field = IntegerField(min_value=0)

        try:
            raw_value = store_data.get("step", 0)
            if raw_value is None or raw_value == "":
                return 0

            # Clean the value first
            clean_value = field.clean(raw_value)

            # Apply max limit manually (clamp to max instead of rejecting)
            return min(clean_value, max_steps)

        except (ValidationError, ValueError, TypeError):
            return 0


class DTOCompatibilityLayer:
    """
    Compatibility layer for integrating secure parsing with existing DTOs.
    """

    @staticmethod
    def create_position_dtos_secure(
        request: HttpRequest, dto_classes: dict[str, type], max_positions: int = 100
    ) -> list[Any]:
        """
        Securely create position DTOs from request data.

        This replaces the existing pattern in position_list.py:
        ```
        number_of_positions = int(request.POST.get("number-of-positions", 0))
        _positions = [parse_position_dtos(request, i) for i in range(1, number_of_positions + 1)]
        ```

        Args:
            request: Django HttpRequest object
            dto_classes: Dict mapping position types to DTO classes
            max_positions: Maximum allowed positions (security limit)

        Returns:
            List of DTO instances
        """
        # Secure position count
        position_count = SecureFormIntegration.secure_position_count(request, max_positions)

        dtos = []
        for i in range(1, position_count + 1):
            position_type_str = request.POST.get(f"position-{i}-type")
            if not position_type_str:
                continue

            dto_class = dto_classes.get(position_type_str)
            if not dto_class:
                continue

            try:
                dto = dto_class.from_request(request.POST, f"position-{i}-")
                dtos.append(dto)
            except Exception:
                # Skip invalid DTOs - could add logging
                continue

        return dtos

    @staticmethod
    def create_nested_dtos_secure(
        data: dict[str, Any], pattern: str, dto_class: type, max_items: int = 100
    ) -> list[Any]:
        """
        Create DTOs from nested form data structure.

        Args:
            data: Form data dictionary
            pattern: Pattern like "position-{i}-nested-{j}-"
            dto_class: DTO class to instantiate
            max_items: Maximum items per level

        Returns:
            List of DTO instances
        """
        # This would use SecureNestedFormParser when integrated
        # For now, provide the interface
        dtos = []

        # Implementation would go here using the SecureNestedFormParser
        # to parse nested structures and create DTOs

        return dtos


class MigrationExamples:
    """
    Examples showing how to migrate the vulnerable code locations.
    """

    @staticmethod
    def migrate_position_list_view():
        """
        Example migration for /app/src/coda/apps/invoices/views/position_list.py:77
        """
        migration_code = """
        # BEFORE (VULNERABLE):
        def existing_positions(request: HttpRequest) -> list[AnyPositionDto]:
            number_of_positions = int(request.POST.get("number-of-positions", 0))  # VULNERABLE
            _positions = [parse_position_dtos(request, i) for i in range(1, number_of_positions + 1)]
            positions = [p for p in _positions if p is not None]
            return positions

        # AFTER (SECURE):
        def existing_positions(request: HttpRequest) -> list[AnyPositionDto]:
            from coda.security.integration import SecureFormIntegration

            number_of_positions = SecureFormIntegration.secure_position_count(request, max_positions=100)
            _positions = [parse_position_dtos(request, i) for i in range(1, number_of_positions + 1)]
            positions = [p for p in _positions if p is not None]
            return positions
        """
        return migration_code

    @staticmethod
    def migrate_htmx_forms():
        """
        Example migration for /app/src/coda/apps/htmx_components/forms.py:24
        """
        migration_code = """
        # BEFORE (VULNERABLE):
        def _total_forms(data: dict[str, Any], prefix: str | None, min_forms: int = 1) -> int:
            prefix = _prefix(data, prefix)
            return int(data.get(prefix + "total_forms", min_forms) or min_forms)  # VULNERABLE

        # AFTER (SECURE):
        def _total_forms(data: dict[str, Any], prefix: str | None, min_forms: int = 1) -> int:
            from coda.security.integration import SecureFormIntegration

            prefix = _prefix(data, prefix)
            return SecureFormIntegration.secure_total_forms(data, prefix, min_forms, max_forms=50)
        """
        return migration_code

    @staticmethod
    def migrate_wizard_step():
        """
        Example migration for /app/src/coda/apps/wizard.py:190
        """
        migration_code = """
        # BEFORE (VULNERABLE):
        def index(self) -> int:
            step = int(self.get_store().get("step", 0))  # VULNERABLE
            if self._out_of_bounds(step):
                step = 0
            return step

        # AFTER (SECURE):
        def index(self) -> int:
            from coda.security.integration import SecureFormIntegration

            step = SecureFormIntegration.secure_wizard_step(self.get_store(), max_steps=20)
            if self._out_of_bounds(step):
                step = 0
            return step
        """
        return migration_code


def get_migration_summary() -> dict[str, str]:
    """
    Get a summary of all required migrations.
    """
    return {
        "position_list.py:77": "Replace int(request.POST.get('number-of-positions', 0)) with SecureFormIntegration.secure_position_count(request)",
        "create.py:65": "Replace int(request.POST.get('number-of-positions', 0)) with SecureFormIntegration.secure_position_count(request)",
        "forms.py:24": "Replace int(data.get(prefix + 'total_forms', min_forms)) with SecureFormIntegration.secure_total_forms(data, prefix, min_forms)",
        "forms.py:283": "Replace int(_form_index) with SecureFormIntegration.secure_form_index(_form_index)",
        "wizard.py:190": "Replace int(self.get_store().get('step', 0)) with SecureFormIntegration.secure_wizard_step(self.get_store())",
    }
