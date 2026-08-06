# DOI Import

The DOI Import feature allows you to create funding requests by entering a DOI (Digital Object Identifier). CODA fetches publication metadata from Crossref, detects funding information, and lets you review and adjust the data before saving.

## Accessing DOI Import

From the [funding requests](fundingrequests.md) overview page, click the **Import** button and select:

- **From DOI** — import a single DOI
- **From DOI (Batch)** — import multiple DOIs at once

## Single DOI Import

### Step 1: Enter a DOI

Enter a DOI (e.g., `10.1038/s41586-020-2649-2`) and click **Import & Preview**.

### Step 2: Preview

CODA fetches the publication metadata from Crossref and displays a preview with:

- **Publication type** — auto-detected as Article or Monograph
- **Publication metadata** — title, authors, DOI, journal/publisher
- **Funding information** — funders detected from the publication's Crossref data

The preview is read-only. You can make adjustments before saving (see below).

### Step 3: Save or Adjust

- Click **Save to Database** to create the funding request immediately
- Or adjust the data first (see Adjusting Import Data)

After saving, you are redirected to the new funding request's detail page where you can make further edits using the regular funding request forms.

## Batch DOI Import

To import multiple publications at once:

1. From the funding requests overview, click **Import** → **From DOI (Batch)**
2. Enter up to 100 DOIs, one per line
3. Click **Fetch & Preview**

The preview page shows a table with status indicators for each DOI:

| Badge | Meaning |
|---|---|
| **OK** | No issues |
| **Warn** | Has warnings (e.g., incomplete metadata) |
| **Mod** | Publication type or funding has been modified |
| **Mod** (outline) | Modified and has warnings |
| **Err** | Failed to fetch metadata |

From the preview page you can:

- Click **View details** on any successful DOI to review and adjust it individually
- Click **Import N publication(s)** to import all successful DOIs at once

After import completes, a result page shows how many publications were imported, skipped, or failed, with links to the new funding requests.

## Adjusting Import Data

Before saving, you can adjust the following on any individual DOI preview:

### Publication Type

If the auto-detected publication type is incorrect:

1. Click the **Change Type** button next to the publication type badge
2. Select **Article** or **Monograph**
3. For articles: search and select the journal
4. For monographs: search and select the publisher
5. Click **Apply**

The preview updates immediately to reflect the new type, including the form fields needed for that publication type.

To revert to the auto-detected type, click **Reset to Auto-Detected**.

### Funding Information

If the auto-detected funders are incorrect or incomplete:

- **Add a funder** — select a funding organization and enter a project ID, then click **Add**
- **Remove a funder** — click the delete button next to a funder entry
- **Reset to auto-detected** — click **Reset to Auto-Detected** to restore the original funding data from Crossref

Only funders that already exist in CODA can be added. If the funding organization isn't in the system yet, create it first in the [Funders](funders.md) section.

## Limitations

- Publications that have already been imported (same DOI) cannot be imported again
- The feature depends on Crossref data availability; some DOI records may have incomplete metadata
- Funding detection relies on funder information provided by the publisher to Crossref and may not cover all cases
