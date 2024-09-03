# Funding Requests

The Funding Requests feature allows your institution to monitor and review incoming requests.

## Overview

The overview page displays a list of Funding Requests and offers various filter options to customize the displayed requests.
A badge displays the current review status, while labels on the right can provide additional means to categorize the request.

```{admonition} Note
The filter options are still limited and will be expanded to allow filtering for arbitrary fields in the future!
```

![](/_static/img/fundingrequests_overview.png)

## Details

Selecting a Funding Request from the overview page will lead to the detail page. Here you will find more information about the Funding Request like journal and publisher data, estimated costs and external funding. Moreover, you have the opportunity to approve or reject the Funding Request on this page or attach labels for additional categorization.

![](/_static/img/fundingrequests_detail.png)

## Creating a new Funding Request

Clicking the `New` button on the overview page opens the Funding Request creation wizard.
The wizard will lead you through separate steps to record the request submitter, information about the publication, the journal and data about estimated cost and funding sources.

### Request Submitter

In the first step we collect information about the Funding Request Submitter like their name, mail address, ORCID, affiliation as well as their roles in the publication.

```{admonition} Note
In future versions we would like to offer the option to gather personal information from ORCID automatically!
```

![](/_static/img/fundingrequests_submitter.png)

### Journal

In the second step we can search and select a journal from CODA's database of over 26000 entries.

![](/_static/img/fundingrequests_journal.png)


### Publication Data

The next step provides you with the opportunity to record meta data about the publication.
This includes title, license, publication type, subject area, open access type, publication state and dates as well as authors and additional references in form of DOIs and links.
The `Publication type` and `Subject area` fields are based on predefined vocabularies that can be configured by the institution hosting CODA. By default, CODA will use [version 3.1 of the COAR Resource Types Vocabulary](https://vocabularies.coar-repositories.org/resource_types/3.1/) for possible publication types and [the DFG subject classification](https://www.dfg.de/resource/blob/331950/85717c3edb9ea8bd453d5110849865d3/fachsystematik-2024-2028-en-data.pdf) for subject areas.

```{admonition} Note
You can paste the author list straight from a PDF into the Authors box and let CODA try to split them up into individual names!
```

![](/_static/img/fundingrequests_publication.png)


### Costs & Funding

The last page of the creation wizard deals with estimated costs and third party funding.
As the final costs of a publication are not always known when a Funding Request comes in, CODA allows you to provide an estimate for the costs. This can be useful when reviewing the Funding Request to determine whether the publication costs exceed the funding limits and further negotiation with a publisher may be necessary.

Furthermore, external funding for a publication can be recorded here. This includes selecting a funding organization from a list of pre-determined funders as well as project ID and name as free text fields. By default, CODA comes with the `Deutsche Forschungsgemeinschaft` and `Bundesministerium für Bildung und Forschung` as possible funding organization selection.

```{admonition} Note
Although currently not yet implemented, future versions of CODA will allow you to add new funding organizations.
```

![](/_static/img/fundingrequests_funding.png)


### What's missing?

**Contracts**

CODA will currently try to find a matching contract by checking if the selected journal is covered by a contract.
However, as managing journal lists for every contract requires a lot of maintenance on the user side, we want to offer adding applicable contracts to publications manually in the future. 