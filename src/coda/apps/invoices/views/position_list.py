"""Invoice position list views.

This module provides backwards-compatible imports. The implementation has been
split into focused modules:
- position_context.py: Context building (funding_sources_context, DefaultContext)
- position_parsers.py: Position parsing (added_positions, parse functions)
- position_views.py: Position CRUD (add/remove positions, invoice_total)
- funding_assignment_views.py: Funding CRUD (add/remove/refresh assignments)
"""

# Context exports
from coda.apps.invoices.views.position_context import (
    DefaultContext as _DefaultContext,
    funding_sources_context,
)

# Parser exports
from coda.apps.invoices.views.position_parsers import (
    added_positions,
    maybe_request_context,
    parse_added_publication_position,
)

# Position view exports
from coda.apps.invoices.views.position_views import (
    add_position,
    invoice_total,
    remove_position,
    render_positions,
    switch_position_tab,
    ErrorDict,
)

# Funding assignment view exports
from coda.apps.invoices.views.funding_assignment_views import (
    add_funding_assignment,
    refresh_unassigned_costs,
    remove_funding_assignment,
    switch_funding_source_type,
)

# Maintain backwards compatibility
__all__ = [
    # Context
    "_DefaultContext",
    "funding_sources_context",
    # Parsers
    "added_positions",
    "maybe_request_context",
    "parse_added_publication_position",
    # Position views
    "add_position",
    "invoice_total",
    "remove_position",
    "render_positions",
    "switch_position_tab",
    "ErrorDict",
    # Funding assignment views
    "add_funding_assignment",
    "refresh_unassigned_costs",
    "remove_funding_assignment",
    "switch_funding_source_type",
]
