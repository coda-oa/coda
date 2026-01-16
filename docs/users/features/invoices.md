# Invoices

CODA's invoice management feature helps you track publication costs by modeling the real invoices your institution receives from publishers and service providers. Invoices connect publications to actual financial transactions and enable comprehensive cost tracking with funding source assignments.

## Overview

You can access invoices from the **Finances** section in the navigation menu. The invoice list shows all invoices in your system with their invoice numbers, creditors, dates, payment status, and total costs.

You can search and filter invoices to find specific transactions quickly. An advanced search can be toggled to filter invoices by various criteria.

![](/_static/img/invoices_list.png)

## Understanding Invoice Structure

An invoice in CODA consists of two main parts:

### Invoice Head

The header contains metadata about the invoice:

- **Invoice Number**: The unique identifier from the creditor (e.g., "INV-2024-12345")
- **Invoice Date**: When the invoice was issued
- **Creditor**: The organization that sent the invoice (selected from your [Creditors](creditors.md) list)
- **Currency**: The currency used for all positions on this invoice
- **Payment Status**: Unpaid, Paid or Rejected
- **External Invoice ID** *(optional)*: Reference ID from external systems
- **Comment** *(optional)*: Notes about the invoice

![](/_static/img/invoices_head.png)

### Invoice Positions

Each invoice contains one or more positions (line items). CODA supports three types of positions:

**Publication Positions**  
Link an invoice position directly to a publication in your system. This is the most common type for Article Processing Charges (APCs).

**Contract Positions**  
Link costs to a publishing contract rather than an individual publication. Used for transformative agreements or consolidated billing arrangements where you pay for the right to publish rather than per-article.

**Free Positions**  
Flexible line items for costs that aren't linked to specific publications or contracts.

Each position includes:
- Cost amount
- Tax rate and calculated tax amount
- Cost type (from the [openCost schema](https://github.com/opencost-de/opencost/blob/main/Cost_types_glossary.md))
- Funding sources (optional cost allocation, see [funding sources](fundingsources.md))
- External position ID (optional reference ID from external systems) 

![](/_static/img/invoices_position.png)

## Creating an Invoice

To create a new invoice:

1. Navigate to **Finances** > **Invoices**
2. Click the **New** button
3. Fill in the invoice head information
4. Add positions (see below)
5. Click the **save** button

![](/_static/img/invoices_create.png)

### Adding Publication Positions

To add a position linked to a publication:

1. In the **Add Positions** section, select the **Publications** tab
2. Search for the publication by title
3. Click **Add** next to the publication you want to invoice
4. The position is added with:
   - Automatic title and funding request link
   - Cost amount (enter the amount charged)
   - Tax rate (defaults to a configured rate, can be adjusted)
   - Cost type (select from openCost types like "Publication Charge")

Multiple publications can be added to the same invoice. Negative amounts can be entered. 

![](/_static/img/invoices_add_publication.png)

### Adding Contract Positions

For invoices related to publishing agreements:

1. Select the **Contracts** tab in the Add Positions section
2. Search for the contract by name
3. Select the contract year
4. Click **Add**
5. Enter the cost amount and select the cost type

Contract positions are useful when you receive consolidated invoices for multiple publications under a single agreement.

![](/_static/img/invoices_add_contract.png)

### Adding Free Positions

For other charges not linked to publications or contracts:

1. Select the **Free Position** tab
2. Enter a description
3. Select the cost type
4. Enter the amount and tax rate
5. Click **Add**

Free positions provide flexibility for all types of publication-related costs.

![](/_static/img/invoices_add_free.png)

## Assigning Funding Sources

After adding positions, you can allocate costs to specific [funding sources](fundingsources.md):

### Single Funding Source

To assign all costs to one budget or institution:

1. Select the funding source type (Budget or Institution)
2. Choose the specific budget or institution

The value in the **amount** field will be associated with the selected budget/institution.

### Split Costs Across Multiple Sources

To divide costs between multiple budgets or institutions:

1. Click **Split** and CODA will change the interface
2. For each assignment, add a new row and enter the amount(s)
3. CODA shows any remaining unassigned costs
4. You can enter net or gross, CODA will display the amounts according to the mode

### Cost Allocation by Institution

When collaborating with partner institutions:

1. Select "Institution" as the funding source type
2. Choose the institution from your [Institutions](institutions.md) directory
3. Enter the amount that institution contributes

This is especially useful for multi-institutional publications where costs are shared.

```{admonition} Unassigned Costs Are Allowed
You don't need to assign all costs to funding sources immediately. CODA allows you to save invoices with partial or no funding assignments, which is useful when budget allocations are still being determined.

However, if you mark an invoice as **Paid**, all costs must be assigned to funding sources.
```

![](/_static/img/invoices_cost_splitting.png)

## Editing Invoices

To modify an existing invoice:

1. Open the invoice detail page
2. Click the **Edit** button
3. Update the invoice head information or positions
4. Add or remove positions as needed
5. Modify funding assignments
6. Click **Save**

## Payment Tracking

CODA tracks three payment states:

**Unpaid** (default)  
The invoice has been received but not yet paid. Funding requests linked to unpaid invoices (by adding publciation positions) are marked as "Invoice Received" in their payment status.

**Paid**  
The invoice has been paid by your institution. Funding requests linked to paid invoices show a "Paid" status.

**Rejected**
Invoices can be marked as rejected when the other two states are not appropriate.

### Marking an Invoice as Paid

1. Open the invoice detail page
2. Click **Pay Invoice**
3. The status changes to Paid
4. All linked funding requests are automatically marked as paid

```{admonition} Payment Validation
When marking an invoice as paid, CODA ensures all positions have funding sources assigned. This prevents paid invoices from having untracked budget allocations.
```

### Resetting Payment Status

If you need to change a paid invoice back to unpaid:

1. Open the invoice detail page
2. Click **Reset Payment**
3. The status returns to Unpaid
4. Publications revert to "Invoice Received" status

## Viewing Invoice Details

The invoice detail page shows:

- Complete invoice head information
- All positions with their types, costs, and funding assignments (as a table)
- Payment status with quick actions to pay or reset
- Total costs: net, tax, and gross amounts
- Currency conversion options (if configured)

### Currency Display

If your invoice includes a currency conversion, you can view costs in different currencies:

1. Use the **Display as currency** dropdown
2. Select the target currency
3. All amounts recalculate using the specified exchange rate

![](/_static/img/invoices_conversion.png)

## Importing Invoices

CODA supports bulk invoice import via JSON files. This is useful for:
- Migrating historical invoice data
- Integrating with external accounting systems
- Batch processing of multiple invoices

To import invoices:

1. Navigate to **Finances** > **Invoices** and click **Import**
2. Prepare your JSON file following the invoice import schema (download and example [here](/_static/downloads/invoices.json))
3. Upload the file
4. CODA validates and creates all invoices and positions
5. Review the import results

The import process automatically:
- Creates new creditors if needed
- Links positions to existing publications or contracts
- Creates funding sources as specified
- Updates publication payment statuses

![](/_static/img/invoices_import.png)

```{admonition} Import Schema
The invoice import schema defines the exact JSON structure required. The schema supports all invoice features including publication positions, contract positions, free positions, funding assignments, and currency conversions. Please prepare your data according to the [example file](/_static/downloads/invoices.json) to match import requirements.
```

## Deleting Invoices

Currently it is not possible to delete invoices from CODA. Future releases intend to implement a soft delete feature to ensure data integrity. 

