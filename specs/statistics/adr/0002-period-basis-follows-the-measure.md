# The period basis follows the measure

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

CODA already has two different reporting periods. The CSV export's period is the request date
(`docs/users/features/csv-export.md`); openCost's period is the paid invoice date
(`docs/users/features/reporting.md`, implemented by selecting paid invoices whose invoice date falls
in the range). Counting requests and publications is naturally dated by the request date; spend is
naturally dated by the paid invoice date. The statistics page therefore uses the request date for
counts and the paid invoice date for spend, and every chart states its basis.

A single uniform basis was rejected because either choice is wrong for the other measure: spend by
request date cannot be reconciled with the openCost reports the institution already submits, and a
publication count by invoice date silently drops everything not yet invoiced.

## Consequences

The two bases are not served by one view: statistics ships request-centric first and invoice-centric
second (ADR-0005), and within the request-centric view the request date is the only basis.
