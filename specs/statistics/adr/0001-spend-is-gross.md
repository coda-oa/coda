# Spend is gross, and is never mixed with decided funding

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

Amounts exist in four places in CODA: the estimated cost of a request, the decided funding of a
review, an invoice position's cost, and a funding assignment's amount. Position and assignment
amounts are stored net of tax; gross is derived (net plus the position's tax rate, while a
`vat`-type position's amount *is* the tax). The statistics page therefore defines **spend** as
invoiced gross, computed through the domain's cost calculation in one place, and never adds it to,
averages it with, or plots it in the same series as decided funding or estimated cost.

The reason is that both mistakes are invisible: summing stored amounts understates every taxed
position, and adding committed money to paid money produces a total that looks plausible and is
wrong. Decisions about what the fund spent have to be made on what was paid.

## Considered Options

- Report net and show tax as a separate figure, the way the invoice list does. Rejected: the
  question the page answers is what was paid, and a reader should not have to add two columns.
- Persist gross columns on positions. Rejected: a second source of truth for the same arithmetic.

## Consequences

On-screen spend will not equal the CSV export's `funded_amount` / `position_amount` columns, which
are net, nor any single column of the invoice list. The page must label the figure "incl. tax" so
nobody reconciles it against the wrong number by hand.
