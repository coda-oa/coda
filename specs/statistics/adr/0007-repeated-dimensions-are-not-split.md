# Dimensions a request can repeat are counted in full, never split

Status: accepted

Scope: a decision of the statistics feature; it changes no other feature, schema or domain rule.

A funding request can attach more than one contract, can name more than one external funder, and can
have more than one corresponding author. A request is counted in full under every value of such a
dimension, and those charts are labelled non-additive: their rows deliberately sum to more than the
total. Dimensions that partition a request's money instead of repeating it — a position's cost type,
and every single-valued publication attribute such as subject area, license or publisher — stay
additive.

Splitting a request evenly across its values would make the column sum by inventing a number the
data does not contain; showing only the first value would hide the others. A labelled non-additive
chart is the only honest option, and the label is what stops a reader treating it as a total.

## Consequences

Non-additive charts must carry the label where a total would normally go, and must not be placed
next to an additive chart without distinguishing them. Which dimensions are non-additive follows
from the model, so adding a dimension to the page means deciding its kind first.
