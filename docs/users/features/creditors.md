# Creditors

The Creditors feature allows you to manage the entities that send invoices to your institution - typically publishers, service providers, or other organizations you pay for publication-related costs. Creditors are essential for organizing invoices and tracking financial relationships.

## Overview

You can access the Creditors page from the **Finances** section in the navigation menu. The overview displays all creditors in your system, showing their names with links to detailed information.

You can search for creditors by name using the search box at the top of the page.

![](/_static/img/creditors_overview.png)

## Understanding Creditors in CODA

A creditor is any organization or entity that sends invoices to your institution for publication costs or related services. Common examples include:

- **Publishers**: Sending Article Processing Charge (APC) invoices
- **Publishing platforms**: For hosting or publication services
- **Aggregators**: Organizations managing payments on behalf of multiple publishers
- **Service providers**: For editing, proofreading, or other publication-related services

Creditors help you:
- **Organize invoices**: Group invoices by who sent them
- **Track relationships**: See all financial activity with each creditor
- **Standardize naming**: Ensure consistency when creating invoices
- **Analyze spending**: Understand which organizations you pay most frequently

```{admonition} Creditors vs. Publishers
While publishers and creditors often overlap, they serve different purposes in CODA:
- **Publishers** are used for journal and publication metadata
- **Creditors** are used specifically for invoice management
- The same organization (e.g., "Springer Nature") might exist as both a publisher and a creditor
```

## Creating a New Creditor

To add a new creditor:

1. Navigate to the Creditors page from the Finances section
2. Click the **New** button
3. Enter the **Creditor Name** (e.g., "Elsevier B.V.", "Taylor & Francis Group")
4. Click **Save**

That's it! Creditors in CODA are intentionally simple - just a name to identify who is billing you.

![](/_static/img/creditors_create.png)


## Viewing Creditor Details

Click on any creditor from the list to see its detail page, which shows:

- **Creditor Name**: The official name as stored in CODA
- **Related Invoices**: A complete list of all invoices from this creditor

### Related Invoices Table

The invoices table displays:
- **Invoice Number**: Click to view the full invoice detail
- **Invoice Date**: When the invoice was issued
- **Amount**: Total invoice amount in the original currency

This view provides a quick overview of your financial relationship with each creditor, making it easy to:
- Track total spending with a specific organization
- Find specific invoices by creditor
- Identify payment patterns or recurring charges

![](/_static/img/creditors_detail.png)

## Editing a Creditor

To update a creditor's information:

1. Navigate to the creditor's detail page
2. Click the **Edit** button (if available in your CODA version)
3. Update the creditor name
4. Click **Save**

![](/_static/img/creditors_update.png)

```{admonition} Note
Editing a creditor name updates it for display purposes, but existing invoices retain the association. All invoices linked to this creditor will show the updated name.
```

## Using Creditors in CODA

Once you've created creditors, they integrate with the invoice management workflow:

### In Invoice Creation

When creating a new invoice:

1. One of the required fields is **Creditor**
2. Select from the dropdown of existing creditors
3. If the creditor doesn't exist yet, you'll need to create it first
4. The selected creditor appears on the invoice detail view

This ensures every invoice is properly attributed to the organization that sent it. You can use the serach field in the invoices section to filter by creditor. 

## Relationship with Publishers

Many creditors will also exist as publishers in CODA's publisher database. Here's how they differ:

### When to Use Each

**Use Publishers when:**
- Creating journals
- Recording publication metadata
- Managing [contracts](contracts.md)
- Linking journals to publishing agreements

**Use Creditors when:**
- Creating invoices
- Recording who sent a bill
- Tracking payment recipients
- Managing financial relationships

