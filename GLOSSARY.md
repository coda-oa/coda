# CODA

CODA manages open-access publication funding requests for a university, from submission and review through invoicing and reporting.

## Language

**Spend**:
Money the institution actually paid out for publications, as invoiced, including tax.
_Avoid_: cost, expense, budget, approved funding

**Decided funding**:
The amount approved for a funding request during review. It is what the fund committed, not what was paid, and it is never added to spend.
_Avoid_: award, grant, approved amount

**Request date**:
The date a funding request was submitted. The period basis for counting requests and publications.
_Avoid_: submission date, application date

**Paid invoice date**:
The date of an invoice that has been paid. The period basis for spend.
_Avoid_: payment date, settlement date

**Funding request**:
A request to fund exactly one publication from the institution's publication fund.
_Avoid_: application, proposal, order

**Corresponding author**:
An author of a publication marked as responsible for it: *Corresponding author* or *Submitting
corresponding author*. A publication may have several. A *Submitter* who is not a corresponding
author does not count, and the request's additional contact is not an author at all.
_Avoid_: contact author, submitter

**Institution**:
An organisational unit of the university, such as a faculty or an institute within one. Authors are
affiliated with institutions, and institutional budgets are funding sources.
_Avoid_: department, organisation. An institute and the faculty above it are two institutions.

**Funder**:
An external organization that funds the research behind a publication, such as a research council or ministry. Recorded on the funding request.
_Avoid_: funding organization, sponsor, grantor, donor. Not to be confused with a funding source.

**Funding source**:
The internal pot of money that pays an invoice position, either a budget of the institution or another institution's budget. Recorded on the invoice.
_Avoid_: fund, account, cost centre, funder

**Report**:
A dated, immutable snapshot of data generated for exchange in a standard format. Today only openCost reports exist.
_Avoid_: calling a live, filterable view a report

**Statistics**:
The live view of spend and publications for a selected period, always computed from current data.
_Avoid_: dashboard, analytics, report

**Dimension**:
An axis the statistics break requests down by: institution, subject area, journal, contract and so on. One record in the dimension registry carries the axis's statistics semantics (kind, measures, additivity) and its page-facing half (facet param, lookup).
_Avoid_: breakdown, grouping

**Facet**:
The filter-form half of a dimension: the GET parameter (or parameters) whose values select the requests behind a chart row. A facet value is what one chart row drills down through.
_Avoid_: filter criterion, chart filter
