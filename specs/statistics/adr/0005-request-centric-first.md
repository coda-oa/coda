# Statistics ships funding-request-centric first, invoice-centric second

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

Everything the page must answer — spend by author, by institution, by subject area, by publisher, by
license, by contract, by funder — is a dimension of a funding request, while the exactness of money
is a property of invoices. Serving both seams in one view was rejected: the request seam and the
invoice seam have different period bases (see ADR-0002) and different row sets, since only invoiced
requests have invoice rows, so a combined view makes "in a given period" ambiguous in the UI and
lets the two sets drift apart.

So statistics ships request-centric: every filter is a request filter, every period is a request
date, every chart's set is a set of funding requests, and spend is the gross sum of the invoice
positions of each request's publication. The invoice-centric view (period = paid invoice date,
reconciling with the openCost reports the institution submits) comes later as its own page.

## Consequences

Spend is dated by request date, so it does not reconcile with openCost reports for now; that
reconciliation is the point of the later view, and the invoice-seam work is deferred rather than
dropped.

A request with no invoice contributes to publication counts and zero to spend — a distribution of
spend therefore has fewer rows than the distribution of publications, and the page must not present
the difference as an error.

Contract positions and free positions carry money but no publication, hence no funding request, so
they are out of scope here. This view makes no claim about the institution's total spend; that claim
belongs to the invoice-centric view.

Because a funding request has exactly one publication, "number of publications" and "number of
funding requests" are the same count in this view.
