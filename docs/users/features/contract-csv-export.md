# Contract CSV Export

The Contract CSV Export feature allows you to export contract data with invoice and cost information for analysis in spreadsheet applications like Excel or LibreOffice Calc. This enables annual reporting, budget tracking for transformative agreements, custom analyses, and data sharing.

## Overview

You can access the Contract CSV Export feature from the **Export** page in the navigation menu. From there, click **View** on the *Contract CSV Export* card to see your previously generated exports.

The export list page displays all contract exports you have created, showing:

- Export name and generation date
- Reporting period (start and end dates)
- Number of records included
- Action buttons for viewing details and downloading

![](/_static/img/contract_csv_export_list_view.png)

```{admonition} Note
CSV exports are generated from your current data, which is stored into snapshots. If you edit data in your CSV export, the snapshot will remain as it is, including an older version of your data.
```

## Understanding CSV Export Data

The CSV export provides a detailed view of your contract-related costs including invoice data, with one row per **funding assignment**. This means:

- A contract with a single invoice position and no cost splitting appears as **one row**
- A contract with cost splitting across multiple funding sources appears as **multiple rows** (one per assignment)

This structure enables precise budget tracking and cost split analysis for transformative agreements and other publishing contracts.

### What Data Is Exported

The CSV file includes the following categories of information:

**Contract Details:**
- Contract name
- Contract period (start and end dates)
- Publishers and journals covered by the contract
- Publication billing method
- Active status
- Contract identifiers (ESAC, OAI, EZB)

**Invoice Information:**
- Invoice number and date
- Creditor name
- Invoice status (paid, unpaid, rejected)
- Invoice currency and comment
- External invoice ID

**Position Details:**
- Position amount
- Tax rate
- Cost type
- Contract year

**Funding Assignment Information:**
- Funded amount
- Funding source name and type (budget or institution)

```{admonition} Note
Only positions linked to a contract are included in this export. Publication positions and free positions are excluded, as they are part of the [Funding Request CSV Export](csv-export.md).
```

## Creating a New CSV Export

To create a new Contract CSV export:

1. Navigate to the **Export** page from the navigation menu
2. Click **View** on the *Contract CSV Export* card
3. Click the **New** button on the export list page
4. Enter a **name** for your export
5. Select the **reporting period** by choosing start and end dates (refers to the invoice date)
6. Apply any desired **filters** to narrow down the data (see below)
7. Click **Create Export**

CODA will gather all contracts with invoices that match your filters and create the export. You will be redirected to the export detail page showing a preview of the data.

![](/_static/img/contract_csv_export_generate_new.png)

### Filtering Options

You can combine filters to control which contracts are included in your export. The following filters are available:

- **Payment Status**: Paid, Unpaid, or Rejected (filters by invoice payment status)
- **Funding Source**: Filter by specific funding source

```{admonition} Tip
Filters control which rows appear in your export, but all columns are always included. This ensures you get a complete dataset for your analysis.
```

## Viewing Export Details

Clicking on an export from the list page shows you detailed information including:

- **Export name** and generation date
- **Reporting period** (start and end dates)
- **Number of records** included
- **Applied filters** — a list of all filters that were used when creating this export
- **Preview** — a table showing the first 50 rows of exported data (or fewer if the export contains less data)

The preview displays a selection of key columns to help you verify the data structure before downloading:

- Contract Name
- Invoice Number
- Position Amount
- Funded Amount
- Funding Source

From the detail page, you can:

- **Download the CSV** file
- **Reuse the filters** to create a new export with the same criteria
- **Delete** the export

![](/_static/img/contract_csv_export_detail_view.png)

```{admonition} Note
The preview only shows the first 50 rows and a subset of columns. Download the full CSV file for complete data.
```

## Downloading the CSV File

To download a CSV export:

1. Navigate to the export list view or the specific export's detail page
2. Click the **Download CSV** button
3. The CSV file will be saved to your device

### CSV Format Details

- **Separator**: Semicolon (`;`)
- **Encoding**: UTF-8
- **Header row**: Column names are included as the first row
- **One row per funding assignment**: Enables detailed cost tracking

```{admonition} Opening in Excel
When opening the CSV file in Excel, you may need to:
1. Use **Data → From Text/CSV** to import the file
2. Select **Semicolon** as the delimiter
3. Choose **UTF-8** encoding
```

## Reusing Export Filters

If you need to create a new export with the same filters:

1. Open the existing export's detail page
2. Click the **Reuse Filters For New Export** button
3. The create form opens with all filters pre-filled (excluding the title and period)
4. Adjust the reporting title, period or filters as needed
5. Click **Create Export**

This is useful for generating regular reports (e.g., quarterly tracking of transformative agreement costs) with consistent filtering criteria.

## Deleting Exports

If you no longer need an export record:

1. Open the export list view or the specific export's detail page
2. Click the **Delete Export** button
3. Confirm the deletion when prompted

```{admonition} Warning
Deleting an export only removes the export record. It does not affect your contracts, invoices, or any other data in CODA.
```
