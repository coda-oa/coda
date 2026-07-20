# Funders (Funding Organizations)

The Funders feature allows you to manage external research funding organizations that support publications at your institution. By maintaining a directory of funders, you can track which external grants or programs contribute to publication costs and ensure consistent naming when creating [funding requests](fundingrequests.md).

## Overview

You can access the Funders page from the **Request Center** section in the navigation menu. The overview displays all funding organizations in your system, showing their names with quick access to each funder's detail page.

You can search for funders by name using the search box at the top of the page. By default, only active (non-archived) funders are shown. Use the **Include archived** checkbox to also display archived funders in the list.

![](/_static/img/funders_overview.png)

## Understanding Funders

Funders (also called Funding Organizations) are external entities that provide financial support for research and publications. Common examples include:

- **Research funding agencies**: Deutsche Forschungsgemeinschaft (DFG), National Science Foundation (NSF)
- **Government departments**: Bundesministerium für Bildung und Forschung (BMBF), European Commission
- **Foundations**: Bill & Melinda Gates Foundation, Wellcome Trust
- **Industry partners**: Corporate research sponsors
- **International organizations**: Horizon Europe, NIH

```{admonition} Funders vs. Funding Sources
These are different features in CODA:
- **Funders** (this page): External research funding organizations that grant money to researchers, used in the last step of the funding request creation process
- **[Funding Sources](fundingsources.md)**: Your institution's internal budgets used to pay invoices

```

## Default Funders

CODA comes pre-configured with two common German funding organizations:

- **Deutsche Forschungsgemeinschaft (DFG)** - Germany's main research funding organization
- **Bundesministerium für Bildung und Forschung (BMBF)** - German Federal Ministry of Education and Research

You can add additional funders as needed for your institution's research portfolio.

## Creating a Funding Organization

To add a new funder:

1. Navigate to **Request Center** > **Funders**
2. Click the **New** button
3. Enter the **Organization Name** and any identifiers (DOI, ROR, Crossref) if needed
4. Click **Save**

The funder is immediately available when creating or editing funding requests.

![](/_static/img/funders_create.png)

## Funder Detail Page

Clicking a funder's name in the list opens its detail page. Here you can view:

- The funder's name and status (Active or Archived)
- Any identifiers associated with the funder (e.g., ROR, CrossRef, DOI)
- A list of all funding requests related to this funder

The detail page provides access to editing, archiving, restoring, and deleting the funder, just like the list view.

![](/_static/img/funder_detail.png)

## Editing a Funding Organization

1. Navigate to the funder's **detail page** or use the button in the funder's list view entry
2. Click the **Edit** button
3. Update the **Name** and any **Identifiers**
4. Click **Save**

All existing funding requests that reference this organization will automatically show the updated name.

## Archiving and Restoring a Funding Organization

Instead of deleting a funder, you can archive it. Archiving removes the funder from the default list view and hides it from the dropdown when creating new funding requests. However, funding requests that already reference the archived funder will continue to work and show it correctly.

To archive a funder:

1. Navigate to the funder's **detail page** or use the button in the funder's list view entry
2. Click the **Archive** button
3. Confirm the archiving in the dialog

To restore an archived funder:

1. Navigate to the **Funders** page and enable the **Include archived** filter
2. Click the archived funder's name to open its detail page or use the restore button from the list view
3. Click the **Restore** button
4. Confirm the restoration in the dialog

Archived funders are excluded from the funder dropdown when creating new funding requests. When editing an existing funding request, the dropdown still includes that request's currently selected archived funder.

## Deleting a Funding Organization

A funder can only be deleted if it is **not** associated with any funding requests.

To delete a funder:

1. Navigate to the funder's **detail page** or use the button in the funder's list view entry
2. Click the **Delete** button
3. If the funder has no related funding requests, confirm the deletion in the dialog
4. If the funder has related funding requests, the dialog explains why it cannot be deleted

## Using Funders in Funding Requests

When creating or editing a funding request, you can specify external research funding. See the [funding request documentation](fundingrequests.md) to learn how to do that.
