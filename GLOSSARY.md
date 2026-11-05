# Coda

Coda manages open-access publication funding: funding requests for publications, their review and decided funding, invoicing of publication costs, and the funding sources those costs are booked against.

## Language

### Finance

**Funding source**:
The account against which publication costs are funded. Two types exist: budget and institution.
_Avoid_: payer, sponsor

**Budget**:
A funding source of type budget: an internal account with a total money amount for a fixed period, in the system-wide currency. The amount is immutable once the period has started; corrections go through transfers or a new budget. Period end does not stop invoices of that period from being booked.
_Avoid_: account, fund, grant

**Budget period**:
The mandatory start/end date range a budget covers. Arbitrary ranges, not calendar-aligned; editable after creation, unlike the amount.
_Avoid_: fiscal year, term

**Cost basis**:
Whether an amount is stated with or without tax: gross-of-tax includes tax, net-of-tax excludes it. Budget commitments are gross-of-tax; position costs are stated net-of-tax.
_Avoid_: tax mode, VAT basis

**Net-of-tax amount**:
An amount excluding tax. Position costs are stated net-of-tax; their funding splits (and the decided funding amount they attribute) are stated gross-of-tax — splits carry no tax rate and count as-is (ADR 0001). A VAT-type cost line is the exception — it states the tax itself, so its net-of-tax amount is nil.
_Avoid_: net (bare), pre-tax

**Gross-of-tax amount**:
An amount including tax: what is actually paid. Budgets reserve and spend gross-of-tax amounts.
_Avoid_: gross (bare), including VAT

**Reserved**:
Money a budget has committed, stated gross-of-tax: the decided funding of approved funding requests, replaced by the assigned amount of an unpaid invoice once one exists.
_Avoid_: allocated, earmarked, promised

**Spent**:
Money a budget has actually paid out via paid invoices, stated gross-of-tax. Never overlaps with reserved for the same money.
_Avoid_: paid, disbursed

**Credited**:
Money added to a budget by an incoming transfer.
_Avoid_: refund, income

**Pending conversion**:
Bookings in a foreign currency whose bank conversion rate has not yet been entered; excluded from converted balances until the rate arrives.
_Avoid_: awaiting rate, unresolved currency

**Overage allowance**:
The optional amount by which a budget may exceed its total; empty means unbounded when going over is allowed.
_Avoid_: buffer, credit line

**Exceeded**:
The derived status of a budget whose commitments (reserved and spent, minus credited and debit) surpass its amount.
_Avoid_: overdrawn, in the red

**Transfer**:
A movement of funds between budgets, booked as debit on the source and credited on the target; may carry an exceeded budget's overrun as debt, with provenance.
_Avoid_: reallocation, carryover

**Debit**:
Money booked against a budget by a transfer: either leaving it or inherited from an exceeded budget's overrun.
_Avoid_: charge, deduction

**Booking ledger**:
The persisted history of budget-relevant events — commitments, payments, transfers — each row recording budget, gross-of-tax amount in the original currency, source reference, and timestamp.
_Avoid_: transaction log, journal

**Institution funding source**:
A funding source of type institution: an institution's cost-sharing account, created automatically per institution and never managed by hand.
_Avoid_: split source

**Decided funding**:
The money amount a review settles for a funding request, as opposed to the request's estimated cost.
_Avoid_: approved amount, grant
