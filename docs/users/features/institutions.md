# Organization Structure

The Organization Structure feature allows you to manage your institution's organizational hierarchy and maintain important institutional identifiers. This is essential for tracking author affiliations and exporting data to standardized formats. 

## Overview

The Organization Structure overview page displays all institutions in your system. Each institution entry shows:

- Institution name
- Parent institution (if the institution is part of a larger organization)
- A toggle switch to control whether the institution can be used as an author affiliation
- Edit button for updating institution details

You can search for institutions by name using the search box at the top of the page.

![](/_static/img/institutions_list_view.png)

## Understanding the "Usable as author affiliation" Toggle

Each institution has a toggle switch labeled **"Usable as author affiliation"**. This setting controls whether an institution appears in dropdown menus when you're adding author affiliations to publications in [funding requests](fundingrequests.md).

**When to enable** (switch ON):
- Departments, faculties, or units that authors typically list as their affiliation
- Research centers or institutes that publish under their own name
- Any organizational unit that should appear in author selection lists

**When to disable** (switch OFF):
- Administrative units that don't publish research
- Organizational placeholders used only for hierarchy management
- Institutions used primarily for internal organization but not for external identification

```{admonition} Note
Disabling this toggle doesn't delete the institution or affect existing publications. It only removes the institution from appearing in future author affiliation selections in the [funding requests](fundingrequests.md).
```

## Institutional Identifiers

CODA supports three types of institutional identifiers that are used for standardized data exchange and reporting:

### ROR (Research Organization Registry)

ROR IDs are persistent identifiers for research organizations worldwide. They look like this: `https://ror.org/02mhbdp94`

ROR IDs are used extensively in scholarly publishing and are required for many funding applications and data reporting standards. They are the preferred primary institution identifier for generating an [openCost report](reporting.md).

**Example**: `https://ror.org/05dxps055`

### ISNI (International Standard Name Identifier)

ISNI is an ISO standard for uniquely identifying contributors to creative works. For institutions, ISNI provides a globally recognized identifier.

ISNI values are 16 digits and can be formatted with spaces or hyphens: `0000 0001 2103 2683` or `0000-0001-2103-2683`

**Example**: `0000 0001 2103 2683`

### Ringgold

Ringgold identifiers are used by many publishers and library systems to identify institutions. They are numeric identifiers without special formatting.

**Example**: `123456`

```{admonition} Note
You can add identifiers to your institutional structure by using the edit button.
```

### Validation

CODA automatically validates institutional identifiers when you enter them:

- **ROR IDs** must follow the format `https://ror.org/` followed by exactly 9 characters
- **ISNI values** must be exactly 16 digits (with or without spaces/hyphens)
- **Ringgold IDs** must be numeric

If you enter an invalid identifier, CODA will show an error message and prevent saving until you correct it.

![](/_static/img/institutions_link_validation.png)

## Creating a New Institution

To add a new institution to your organizational structure:

1. Click the **New** button on the Organization Structure overview page
2. Fill in the **Basic Information**:
   - **Name**: The full name of the institution (e.g., "Department of Biology")
   - **Internal ID**: You can provide a custom identifier, or leave blank to auto-generate one (format: `inst_XXXXXXXX`)
   - **Parent**: Optionally select a parent institution to create hierarchical relationships
   - **Usable as author affiliation**: Check this box if authors should be able to select this institution when adding their affiliations

3. Add **Institution Identifiers** (optional but recommended):
   - Click **Add** to create a new identifier row
   - Select the identifier type (ROR, ISNI, or Ringgold)
   - Enter the identifier value
   - You can add multiple identifiers of different types

4. Click **Save** to create the institution

![](institution_new.png)

```{admonition} Tip
You can add multiple rows to include all relevant identifiers for your institution. For example, you might add both a ROR ID and an ISNI for the same organization.
```

## Editing an Institution

To update an existing institution:

1. Click the **Edit** button next to the institution you want to modify
2. Update any of the basic information fields
3. Add, modify, or remove identifiers as needed
4. Click **Save** to apply your changes

![](/_static/img/institutions_edit_view.png)

```{admonition} Note
If publications or contracts are already linked to an institution, updating the institution's identifiers will ensure future exports use the updated values. However, previously generated reports (like [openCost exports](reporting.md)) are snapshots and won't be affected.
```

## Organizational Hierarchies

CODA supports hierarchical organization structures by allowing you to set parent-child relationships between institutions. This is useful for representing your institution's actual organizational structure.

**Example hierarchy**:
- University of Example (parent)
  - Faculty of Sciences (child of University)
    - Department of Biology (child of Faculty)
    - Department of Chemistry (child of Faculty)
  - Faculty of Humanities (child of University)

To create a hierarchy:
1. Create the top-level institution first (e.g., "University of Example")
2. When creating child institutions, select the parent from the **Parent** dropdown

The overview page will display these relationships by showing "Part of [Parent Name]" under each child institution.

## Importing Institutions from CSV

For bulk operations, CODA allows you to import multiple institutions at once from a CSV file. This is particularly useful when:

- Setting up CODA for the first time with your complete organizational structure
- Updating identifiers for many institutions at once
- Importing institutions from another system

### CSV File Format

Your CSV file should use **semicolons (;)** as separators and include the following columns:

```
internal_id;name;ROR;ISNI;Ringgold;parent;usableAffiliation;archived
```

**Column descriptions**:
- **internal_id** (optional): A unique identifier for the institution in CODA.  If not provided, CODA will auto-generate one. Use this to link parent institutions and for reliable re-imports.
- **name** (required): The institution's full name
- **ROR** (optional): ROR identifier URL
- **ISNI** (optional): ISNI value (16 digits)
- **Ringgold** (optional): Ringgold numeric ID
- **parent** (optional): The internal_id of the parent institution (see below)
- **usableAffiliation** (optional): `true` or empty to enable as author affiliation, `false` to disable
- **archived** (optional): `true` to mark institution as archived, `false` or empty for active institutions

**Example CSV**:
```csv
internal_id;name;ROR;ISNI;Ringgold;parent;usableAffiliation;archived
inst_ABC123;University of Example;https://ror.org/02mhbdp94;;;;;true;false
inst_XYZ789;Faculty of Sciences;;;123456;inst_ABC123;true;false
inst_BIO456;Department of Biology;https://ror.org/05dxps055;0000000121032683;;inst_XYZ789;false;false
```

You can download an example schema file [here](/_static/downloads/CODA_Institutes_example_file.csv). 

### Understanding the Parent Column

The `parent` column uses **internal_id** values to reference parent institutions. This makes hierarchies more maintainable and allows you to reorder rows without breaking relationships.

**Example from the CSV above**:
- Row 1: "University of Example" (internal_id=inst_ABC123, no parent)
- Row 2: "Faculty of Sciences" (internal_id=inst_XYZ789, parent=inst_ABC123)
- Row 3: "Department of Biology" (internal_id=inst_BIO456, parent=inst_XYZ789)

This creates: University → Faculty → Department

```{admonition} Auto-Generated IDs
If you don't provide internal_id values in your CSV, CODA will automatically generate them (format: `inst_XXXXXXXX`). You can export your institutions later to get the generated IDs for future updates.
```

### Import Process

To import institutions:

1. Click the **Import** button on the Organization Structure overview page
2. Click **Choose File** and select your CSV file
3. Click **Import** to upload and process the file

![](/_static/img/institutions_import.png)

CODA will:
- Create new institutions that don't exist
- Update existing institutions using smart matching (see below)
- Set archived status based on the `archived` column (active institutions can be archived, and archived institutions can be reactivated)
- Validate all identifiers and skip invalid ones (import institution but without identifier)
- Show a summary of successful imports and errors, if any

```{admonition} Smart Matching Priority
When importing, CODA uses the following priority to match institutions:

1. **internal_id** (highest priority): If provided and matches an existing institution, that institution is updated
2. **External identifiers**: If the institution has a matching ROR, ISNI, or Ringgold ID, it will be updated
3. **Name matching**: If no ID matches, CODA matches by institution name

This makes it safe to re-import updated files - institutions with internal_id will be reliably matched and updated instead of creating duplicates.
```

### Import Results

After importing, CODA will display:

- **Total institutions processed**
- **Matching statistics**: How institutions were matched (by internal_id, by external identifier, or created new)
- **Fully imported**: Institutions created/updated without any issues
- **Partially imported**: Institutions created but with some invalid identifiers that were skipped
- **Error details**: Which institutions had problems and what the issues were

### Handling Import Errors

Common import errors include:

- **Invalid ROR format**: Make sure ROR IDs start with `https://ror.org/`
- **Invalid ISNI format**: ISNI must be exactly 16 digits
- **Invalid Ringgold**: Must be a numeric value
- **Parent reference errors**: Make sure the parent internal_id matches an existing institution
- **Duplicate internal_id**: Each internal_id must be unique

If an institution has an invalid identifier, CODA will still import the institution but skip the problematic identifier. This allows your import to continue even if some data needs correction.

## Exporting Institutions to CSV

You can export all your institutions to a CSV file for backup, reporting, or updating in bulk. The export includes all institution data including auto-generated internal_id values.

To export institutions:

1. Click the **Export** button on the Organization Structure overview page
2. A CSV file will be downloaded to your computer with all current institutions

The exported CSV file:
- Includes all institutions (both active and archived)
- Contains all identifiers (ROR, ISNI, Ringgold) and internal_id values
- Includes the archived status for each institution
- Uses the same format as the import CSV, so you can modify and re-import it
- Shows parent relationships using internal_id values

```{admonition} Round-Trip Workflow
You can export institutions, modify the CSV file (e.g., update names, add identifiers, change hierarchies), and then re-import the file. CODA will use the internal_id column to reliably match and update existing institutions.
```

## What's Next?

We're working on enhancements to make institution management easier by enabling deletion of e.g. erroneously created institutions. 




