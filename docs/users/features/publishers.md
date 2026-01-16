# Publishers

The Publishers feature helps you manage the organizations that publish academic journals and monographs. By maintaining a directory of publishers, you can link journals to their publishing houses, manage transformative agreements, and ensure consistency across your institution's publication tracking.

## Overview

You can access the Publishers page from the **Journals & Publishers** section in the navigation menu. The overview displays all publishers in your system with their names, block status, and quick access to editing.

You can search for publishers by name using the search box at the top of the page.

![](/_static/img/publishers_overview.png)

## Understanding Publishers in CODA

Publishers are the organizations that publish journals, books, and other academic materials. In CODA, publishers serve several important roles:

- **Journal management**: Each journal is linked to one publisher
- **Contract organization**: Transformative agreements are associated with publishers
- **Monograph publishing**: Book publishers are tracked for monograph funding requests
- **Blocklist management**: Publishers can be flagged to prevent funding certain publications

Common examples of publishers include:

- **Commercial publishers**: Elsevier, Springer Nature, Wiley, Taylor & Francis
- **Society publishers**: American Chemical Society, IEEE, Royal Society of Chemistry
- **University presses**: Oxford University Press, Cambridge University Press
- **Open access publishers**: PLOS, MDPI, Frontiers Media
- **Independent publishers**: Smaller academic publishing houses

```{admonition} Publishers vs. Creditors
These are different entities in CODA:
- **Publishers** publish journals and academic content
- **[Creditors](creditors.md)** send invoices for publication costs

While often the same organization (e.g., "Springer Nature" as both publisher and creditor), they serve different purposes in the system.
```

## Creating a Publisher

To add a new publisher:

1. Navigate to the Publishers page
2. Click the **New** button
3. Enter the **Publisher Name** (e.g., "Springer Nature", "Elsevier", "PLOS")
4. Click **Save**

The publisher is immediately available for linking to journals, contracts, and monographs.

![](/_static/img/publishers_create.png)

```{admonition} Naming Best Practices
Use the publisher's official corporate name:
- "Springer Nature" not "Springer" or "Nature Publishing Group"
- "Taylor & Francis Group" not "T&F"
- "Public Library of Science" or "PLOS" (choose one and be consistent)
- Check the publisher's website for their official name
```

## Editing a Publisher

To update a publisher's name:

1. Navigate to the Publishers page
2. Find the publisher you want to edit
3. Click **Edit**
4. Update the **Name**
5. Click **Save**

All journals, contracts, and publications linked to this publisher automatically reflect the updated name.

![](/_static/img/publishers_edit.png)

```{admonition} Important
Editing a publisher's name updates it everywhere in CODA. This affects:
- All journals published by this organization
- All contracts with this publisher
- Historical data and reports

Use this carefully for corrections or standardization, not to repurpose a publisher entry.
```

## Publisher Blocklist

CODA includes a blocklist feature to flag publishers your institution wants to avoid:

### Blocking a Publisher

From the publisher list:

1. Locate the publisher you want to block
2. Click the **Block** button
3. The publisher is immediately added to your blocklist

Blocking a publisher helps your team identify potentially problematic publishing relationships during funding request review.

### Unblocking a Publisher

If a publisher should no longer be blocked:

1. Find the blocked publisher in the list (they show an **Unblock** button)
2. Click **Unblock**
3. The publisher is immediately removed from the blocklist

For more information about managing blocked journals and publishers, see the Blocklist documentation (coming soon).

## Using Publishers in CODA

Publishers are referenced throughout CODA in several contexts:

### In Journals

Every [journal](journals.md) is associated with one publisher:

- When creating a journal, you select its publisher
- Journal listings display the publisher name
- Publisher changes can be tracked through journal updates

This connection ensures accurate representation of who publishes each journal.

### In Contracts

[Transformative agreements](contracts.md) specify which publishers are party to the deal:

- Contracts can include multiple publishers (for publisher groups)
- Publishers are searched and added when creating contracts
- Contract coverage is determined by publisher and journal relationships

This enables automatic detection of publications covered by institutional agreements.

### In Monograph Funding Requests

When creating funding requests for books or monographs:

- You search for and select the book publisher
- The publisher information is stored with the publication
- This helps track monograph funding across different publishers

### In Automatic Import

When importing funding requests or journals:

- If a publisher with the specified name exists, it's reused
- If the publisher doesn't exist, CODA creates it automatically
- This prevents duplicate entries and ensures completeness

## Searching for Publishers

The publisher list supports simple search:

**Search by name**: Enter any part of the publisher's name
- "springer" finds "Springer Nature", "Springer", etc.
- "oxford" finds "Oxford University Press"
- Search is case-insensitive

Results update as you type, making it easy to find the publisher you need.

## Viewing Publisher Information

Currently, publishers don't have a dedicated detail page. Instead:

- The list view shows all essential information
- Clicking a publisher name searches for that publisher in the list
- Block status is visible directly in the list
- Edit functionality is accessible from each list item

```{admonition} Future Enhancement
In future versions, publisher detail pages will show:
- All journals published by this organization
- Contracts that include this publisher
- Statistics on publications and costs
- Historical publication activity
```

## Common Questions

**Can I delete a publisher?**  
Deletion is only possible if the publisher has no linked journals, contracts, or publications. This protects data integrity. If you need to remove a publisher with existing references, consider blocking them instead.

**What happens if a publisher merges with another?**  
Create a new entry with the merged company name and update journals/contracts as appropriate. You can keep old publisher entries for historical accuracy or update them to reflect the new organization.

**How many publishers should I create in advance?**  
Only create publishers you know you'll need. CODA automatically creates publishers during imports, so you don't need to pre-populate the entire database. Focus on major publishers your institution works with regularly.

**Should I create separate entries for imprints?**  
It depends on your tracking needs. Major imprints with distinct identities can be separate publishers (e.g., "Nature Portfolio" vs "Springer"). Minor imprints can usually be tracked under the parent publisher.

**What's the difference between blocking a publisher and blocking a journal?**  
Blocking a publisher flags all their journals, while blocking a journal targets a specific publication. Publisher blocks are broader and useful for policy-level decisions (e.g., avoiding predatory publishers). Journal blocks are more granular.

**Can one journal have multiple publishers?**  
No. Each journal entry has exactly one publisher. If a journal changes publishers, you would typically update the publisher link or create a new journal entry with a predecessor/successor relationship.

**Do I need to match publisher names exactly as they appear in external databases?**  
Not necessarily. Use the names that make sense for your institution. However, consistency is important—decide on one name and use it everywhere (e.g., "PLOS" vs "Public Library of Science").

## Best Practices

### Naming Conventions

- Use official corporate names from the publisher's website
- Be consistent with abbreviations (decide on "PLOS" or "Public Library of Science" and stick with it)
- Avoid special characters that might cause issues in exports
- Include country codes only when necessary to distinguish publishers with similar names

### Organization

- Create major publishers before importing large datasets
- Establish naming conventions and document them for your team
- Periodically review the publisher list for duplicates or variations
- Standardize names that have changed over time (e.g., "Springer" → "Springer Nature")

### Integration

- Let imports create publishers automatically rather than pre-creating everything
- Update publisher information when organizations merge or rebrand
- Link publishers to contracts as agreements are established
- Use blocking strategically for institutional policy enforcement

### Data Quality

- Verify publisher names before creating new entries
- Check for existing publishers before adding duplicates
- Keep one person responsible for publisher data quality
- Document the reasoning behind publisher blocks for your team

## What's Next?

- **[Journals](journals.md)**: Link journals to their publishers
- **[Contracts](contracts.md)**: Associate transformative agreements with publishers
- **[Creditors](creditors.md)**: Understand the difference between publishers and billing entities
- **Blocklist** (coming soon): Learn more about blocking publishers and journals

---

Publishers provide organizational structure for your institution's publication ecosystem, connecting journals, contracts, and costs under the organizations that make academic publishing possible.
