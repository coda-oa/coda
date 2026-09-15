"""Turning a report's items into an openCost document.

``live`` is the package's entry point: ``transform_report`` walks the report's own item rows and
returns the document openCost accepts, or ``None`` when the items hold nothing openCost can
express. What it left out on the way — entities, invoices, invoice rows — is collected into the
run's issue list rather than raised, together with how every row fared.

The other modules hold one construction each: ``publication`` and ``contract`` for the two kinds
of report item, ``invoices`` for the invoice elements within them, and ``entities`` for the
institution and exclusion wording both of those need. Their per-item builders are reached by
``live`` and directly by the tests that exercise one kind of item alone.
"""
