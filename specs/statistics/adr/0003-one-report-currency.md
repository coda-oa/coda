# Report in one currency, and drop what cannot be converted

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

Positions carry their own currency and an invoice may carry one conversion to a target currency;
mixed-currency monetary fields inside a single invoice are invalid (the openCost invoice line
asserts it: "VAT and amount-paid values must use the same currency"). The statistics page reports in
one configured currency, converting each invoice with its stored rate. Amounts already in the report
currency need no rate. Amounts in another currency whose invoice has no rate are excluded from the
totals and counted visibly on the page, with a way to reach the affected invoices.

Summing mixed currencies produces a number with no meaning, and assuming a rate of one produces a
number that looks right and is not — the worst possible failure for a page used to make funding
decisions.

## Consequences

Totals are lower than the raw data implies while exchange rates are missing, and the page says so
rather than hiding it. The excluded amount is itself a data-quality signal the institution can act
on.
