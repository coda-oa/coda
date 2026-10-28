# Dashboards are packages inside the reporting app

Status: accepted

Scope: a decision about the structure of `apps/reporting/` and where future
statistics dashboards live. It changes no behavior, schema or domain rule.

## Context

The reporting app currently holds one dashboard: the funding-request statistics
page. Its request-specific parts (`views/page.py`, `dataset.py`, `queries.py`,
the facet half of `drilldown.py`) are entangled with its reusable parts (the
`_url`/lookup-table mechanics in `drilldown.py`, `treemap.py`, the shared filter
rail in `apps/listfilters.py`, the generic template partials, `reporting.js`).
More dashboards are planned — reporting on other aspects than funding requests.

The pure engine (`contexts/statistics/`) is deliberately dashboard-independent:
dimensions are a registry, `RequestFact` is a generic grain, and nothing in it
imports any app. A new dashboard's job is to build `RequestFact`s from its own
domain and register its dimensions — the aggregation, chart and timeline
machinery come for free.

## Decision

Each dashboard is a **package inside `apps/reporting/`**, holding everything
only that dashboard needs:

```
apps/reporting/
    views/home.py                 # the hub listing dashboards
    fundingrequests/              # one package per dashboard
        views.py
        dataset.py                # domain -> RequestFact adapter
        queries.py
        drilldown.py              # this dashboard's facet params
        templates/reporting/fundingrequests/
    shared/
        drilldown.py              # _url / lookup-table mechanics
    treemap.py                    # institution hierarchy — reusable
```

The shared skeleton (band form, tab groups, region/OOB wiring) is extracted
from `views/page.py` **only when the second dashboard exists** — with one
consumer, any abstraction is a guess.

Names stay stable: the app is `reporting`, the URL namespace is `reporting:`,
and the existing URL name `reporting:stats_fundingrequests` keeps its meaning
("the statistics page for funding requests") under future siblings like
`reporting:stats_publications`.

## Considered Options

- Rename the app (`reporting` → `dashboards`). Rejected: URL namespace,
  breadcrumbs in three other apps (`opencost`, `exports`, `nav_tags`) and the
  template tree all reference it, for no expressiveness gain — the per-package
  names carry the structure.
- Move `contexts/statistics/` under `apps/reporting/`. Rejected: the pure
  engine's DB-free test suite and its independence from any single dashboard
  are the reason new dashboards are cheap; embedding it in a Django app
  forfeits both.
- One flat app, no packages. Rejected: with a second dashboard, `page.py`
  becomes a grab-bag and the per-dashboard adapter files become ambiguous.

## Consequences

`page.py` stays as-is until the second dashboard materializes; the first
dashboard's extraction is then mechanical because the pure layer never coupled
to funding requests. Every new dashboard must build `RequestFact`s and register
dimensions — it must not reach into another dashboard's dataset, and the shared
machinery must not grow knowledge of any single dashboard.
