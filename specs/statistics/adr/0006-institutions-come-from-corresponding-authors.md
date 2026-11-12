# Institutions are attributed through the corresponding author's affiliation, as recorded

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

The institution dimension attributes a request's publications and spend to the institution recorded
as the affiliation of the publication's corresponding authors — an author marked *Corresponding
author* or *Submitting corresponding author*. A plain *Submitter* does not count, and the request's
extra contact is not an author. The institution is reported exactly as recorded: an institute and
its faculty are separate institutions, and nothing is rolled up.

The question this dimension answers is whose work the money paid for, and the affiliation is the
only record of that. Roll-ups would silently merge distinct units and make a bar impossible to trace
back to the rows behind it.

## Considered Options

- The institution of the funding source (cost splitting). Rejected for this dimension: it answers
  who paid internally, which is a different question, and it is already served by the funding-source
  dimension.
- Roll up to the top-level institution or a chosen depth. Rejected: the tree is an organisational
  convenience, not a reporting hierarchy.

## Consequences

Requests whose publication has no corresponding author, and corresponding authors with no recorded
affiliation, land in explicit buckets rather than disappearing. Because grouping is exactly as
granular as data entry, consistent affiliation naming now matters for the charts: two spellings of
one institute are two bars.
