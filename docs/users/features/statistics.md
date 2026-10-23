# Funding Request Statistics

The statistics page tells you at a glance how many publications your institution requested funding for, what they cost, and where the money and the publications come from. It is part of the [Reporting](reporting.md) area: open **Reporting** in the navigation menu and choose *Funding Request Statistics*.

Everything on the page is computed live from your current data: change a filter and the numbers update immediately, nothing needs to be generated first.

![](/_static/img/statistics_overview.png)

A few terms used throughout this page:

- A **publication** is one funding request. Requests that have not been invoiced yet still count here, they just don't contribute anything to the spend.
- **Spend incl. tax** is the gross amount of the paid invoice positions behind the requests, in your institution's home currency (set under *Preferences*).
- The **reporting period** is the date range you pick in the toolbar. Everything on the page refers to it.

## Filtering

The page uses the same filters as the funding request list: search by title, author, journal, publisher or ID, and, behind the **Filters** button, status, publication type, labels, contracts and more. Active filters show up as removable chips above the results, and a counter on the Filters button tells you how many are in effect.

The date range in the toolbar selects the reporting period. Without a date range the page covers everything; with one, the toggle next to it switches on the [comparison](#comparison) with the preceding period.

## Overview tab

The overview opens with the headline cards. The first four need little explanation: publications funded, spend including tax, average spend per request, and the top-5 share, the portion of the spend that the five largest requests account for.

The two cards below them are the honest bookkeeping: how many requests in the period have **no invoice yet** (they count as publications but not in the spend), and how many had amounts **excluded** because their invoices cannot be converted to the home currency. If any are excluded, a notice above the statistics lists the affected invoices by number, so nothing disappears silently.

Below the cards, the timeline shows request counts per week, month or quarter, and you switch the resolution right on the chart. The timeline always buckets by request date, no matter when the matching invoices were paid.

On the **Attribution** tab you'll also find the institution hierarchy as a treemap: the area of each rectangle is the number of publications, the colour the spend. Unlike the institution section's table, the treemap aggregates institution subtrees, so you can read the big picture at faculty level; a request appears in full under every one of its affiliations, which is why subtrees can overlap.

![](/_static/img/statistics_institution_treemap.png)

## Comparison

Flip the toggle next to the date range and the page loads the previous period, the equally long window directly before yours, and marks it throughout in a lighter shade.

The headline cards now show the change versus the previous period, e.g. *+8%* publications, *−13%* spend. In the charts, the previous period appears as muted bars next to the current ones; the table values gain the signed percentage under each figure, and a value that exists only now shows as "new". You can see all of this in the section screenshots below.

```{admonition} Note
For institutions, contracts and funding sources, one request contributes its **full** amount under every matching value, which means spend numbers in those sections are deliberately double-counted, and comparing them across periods would compare inflated numbers. There, comparison covers the publication counts; spend is only compared in the sections where values add up.
```

## Dimension sections

The tabs group the breakdowns by theme:

| Tab | Sections |
|---|---|
| **Overview** | headline cards, timeline, institution treemap |
| **Publication** | subject area, publication type, publication form, license, open access type |
| **Venues** | journal, publisher |
| **Cost & contracts** | cost type, contract, funding source |
| **Attribution** | institution, funder |

Each section pairs a chart with a table of exact values. The chart plots the two measures side by side (publications and spend incl. tax, each with the previous period in a lighter shade) and collapses the table under an *Exact values* expander to keep the page scannable. Every row links to the matching funding requests in the list view, with the same filters, so you can drill down from any bar or table cell.

![](/_static/img/statistics_sections_chart.png)

The table adds the comparison as signed percentages under each value ("new" where the previous period has none) and a total row, with the caveat noted above where totals do not exist.

![](/_static/img/statistics_sections_table.png)

### How the numbers behave

- **Institutions** come from the request's *corresponding author* affiliations, exactly as recorded. The sections do not roll a department up into its parent institution.
- A request with several institutions, contracts or funding sources appears **once per value, with its full amount**. That is why the values in those sections don't add up to the headline, see the [comparison](#comparison) note.
- **Funding source** shows how much was *funded by* each source. Amounts on invoice positions without a funding assignment appear as *Unassigned* (only when non-zero), and the funded-by values plus that remainder always sum to the spend.
- The **funder** section counts requests per external funder and carries no money figures.
- Whatever a facet cannot attribute (a request with no corresponding author, no subject area) lands under an explicit *Unknown* row instead of being dropped.

## Currency

All money is reported in your institution's **home currency**. Amounts already in that currency are taken as they are; anything else needs a currency conversion on its invoice that targets the home currency.

```{admonition} Warning
Requests whose invoices cannot be converted are **excluded from all spend figures**. The overview's "Requests with excluded amounts" card and the notice above the statistics tell you which invoices are affected and how many requests that touches.
```
