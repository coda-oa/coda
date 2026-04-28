"""Query services for funding request read-side operations.

Following CQRS-lite pattern:
- Queries are separate from commands (repository)
- Return detail models optimized for views
- Use domain models where sufficient
- Optimize DB queries with joins/prefetches

Function-based (not class-based) for simplicity (KISS).
"""
