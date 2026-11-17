// Renders the server-built plotly figures of the statistics page (plan §9).
// Each [data-chart] mount names the json_script carrying the figure — the exact
// {data, layout, config} object Plotly.newPlot consumes. No inline JS, no
// escaping work here: the template owns the payloads, this file only paints.
// Runs on first load and after every htmx swap of the statistics region, so a
// filter change re-paints the freshly swapped charts.

// Commit-on-blur for the band form's date fields and search box. htmx cannot
// express "changed since focus": its `changed` modifier compares against the
// *listener* element's value (the form), so no hx-trigger spelling of this
// exists — the per-field value must be tracked in JS. The search box gets no
// input debounce (search-as-you-type would run the whole pipeline), so blur
// is its only commit besides Enter.
//
// focusout (unlike blur) bubbles, and the form is never htmx-swapped, so one
// delegated listener on the form survives the period block's OOB re-renders.
const COMMIT_ON_BLUR =
    ".filter-search, #id_start_date, #id_end_date, #id_compare_start_date, #id_compare_end_date";
const bandForm = document.getElementById("filter-toolbar-form");
// Module scope so the previous-period button's commit below can also re-seed
// it; otherwise the next blur of a compare input re-fires an identical
// request for the values the button just wrote.
const lastCommitted = new WeakMap();
if (bandForm) {
    // Seed the baseline on focus: only a value that changed while the field
    // was focused commits on its blur. Without the seed the first blur of an
    // untouched field (lastCommitted undefined) would fire — exactly the
    // search<->date tab-switch requests this listener exists to prevent.
    bandForm.addEventListener("focusin", (event) => {
        const field = event.target;
        if (field.matches(COMMIT_ON_BLUR) && !lastCommitted.has(field)) {
            lastCommitted.set(field, field.value);
        }
    });
    // A submit serializes the fields' current values, so the blur path has
    // nothing new to commit afterwards. Without the re-seed, "type into
    // search + Enter, then blur" fires a second, identical request: the
    // blur's change rides the trigger's 300ms delay, queues behind the
    // submit via hx-sync, and still runs after the swap.
    bandForm.addEventListener("submit", () => {
        for (const field of bandForm.querySelectorAll(COMMIT_ON_BLUR)) {
            lastCommitted.set(field, field.value);
        }
    });
    bandForm.addEventListener("focusout", (event) => {
        const field = event.target;
        if (!field.matches(COMMIT_ON_BLUR)) {
            return;
        }
        if (lastCommitted.get(field) === field.value) {
            return;
        }
        lastCommitted.set(field, field.value);
        // Dispatch change on the FORM, not the field: the band's change
        // trigger excludes date inputs by design (segmented typing commits
        // `change` mid-edit), so a change on the date field itself would be
        // filtered out. On the form, event.target is the form — which
        // matches neither excluded selector — and the trigger's 300ms
        // debounce coalesces rapid blurs like an editor-committed value.
        bandForm.dispatchEvent(new Event("change", { bubbles: true }));
    });
}

// The comparison period controls (filter_period.html). The compare inputs
// commit on blur like the report dates (COMMIT_ON_BLUR above); the rest is
// the switch's enable/disable and the previous-period button. The period
// block re-renders out of band on every region response, so the state is
// re-derived from the DOM after each swap.
const compareControls = (root) => {
    const switchInput = root.querySelector("#compare-switch");
    const inputs = root.querySelectorAll(
        "#id_compare_start_date, #id_compare_end_date"
    );
    const previousButton = root.querySelector("#compare-previous-button");
    return { switchInput, inputs, previousButton };
};

const priorWindow = (startValue, endValue) => {
    // The same-length window immediately before [start, end] — the client
    // copy of the view's DateRange.prior_window. Empty or unparseable bounds
    // disable the button instead of guessing.
    const start = new Date(startValue);
    const end = new Date(endValue);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
        return null;
    }
    const length = Math.round((end - start) / 86400000) + 1;
    const priorEnd = new Date(start);
    priorEnd.setDate(priorEnd.getDate() - 1);
    const priorStart = new Date(priorEnd);
    priorStart.setDate(priorStart.getDate() - (length - 1));
    return [priorStart.toISOString().slice(0, 10), priorEnd.toISOString().slice(0, 10)];
};

const syncCompareControls = (root) => {
    const { switchInput, inputs, previousButton } = compareControls(root);
    if (!switchInput) {
        return;
    }
    const on = switchInput.checked;
    inputs.forEach((input) => {
        input.disabled = !on;
    });
    if (previousButton) {
        const [startInput, endInput] = root.querySelectorAll(
            "#id_start_date, #id_end_date"
        );
        previousButton.disabled = !on || !priorWindow(startInput?.value, endInput?.value);
    }
};

if (bandForm) {
    syncCompareControls(bandForm);
    // The switch's change rides the band's change trigger (300ms debounce),
    // so toggling submits the form like any filter edit; the server
    // re-renders the block OOB with the inputs enabled and prefilled.
    bandForm.addEventListener("change", (event) => {
        if (event.target.id === "compare-switch") {
            syncCompareControls(bandForm);
        }
    });
    // type=button: write the prior window into the compare inputs, re-seed
    // the blur baselines, then dispatch change on the FORM so the band's
    // change trigger picks it up.
    bandForm.addEventListener("click", (event) => {
        if (!(event.target instanceof Element) || event.target.id !== "compare-previous-button") {
            return;
        }
        const { inputs } = compareControls(bandForm);
        const [startInput, endInput] = bandForm.querySelectorAll("#id_start_date, #id_end_date");
        const window_ = priorWindow(startInput?.value, endInput?.value);
        if (!window_ || !inputs.length) {
            return;
        }
        const [compareStart, compareEnd] = inputs;
        compareStart.value = window_[0];
        compareEnd.value = window_[1];
        // Re-seed the blur baselines: the button just committed these values.
        lastCommitted.set(compareStart, compareStart.value);
        lastCommitted.set(compareEnd, compareEnd.value);
        bandForm.dispatchEvent(new Event("change", { bubbles: true }));
    });
    document.addEventListener("htmx:afterSettle", (event) => {
        if (event.target instanceof Element && event.target.querySelector("#compare-switch")) {
            syncCompareControls(event.target);
        }
    });
}

const renderChart = (element) => {
    const source = document.getElementById(element.dataset.chart);
    if (!source || element.dataset.plotlyRendered === "true") {
        return;
    }
    const figure = JSON.parse(source.textContent);
    const config = { responsive: true, ...figure.config };
    element.dataset.plotlyRendered = "true";
    Plotly.newPlot(element, figure.data, figure.layout, config).then(() => {
        if (figure.tile_links) {
            attachTileLinks(element, figure.tile_links);
        }
    });
};

// Leaf tiles filter (like the table-row links), branch tiles keep plotly's
// drilldown. Lookup is by point.id: a branch and its own-publication row
// share a display label, and the id is stable across drilldown — pointNumber
// indexes the drilled view, point.label collides for the shared label.
const attachTileLinks = (element, tileLinks) => {
    element.on("plotly_treemapclick", (event) => {
        const point = event?.points?.[0];
        if (!point) return;
        const link = tileLinks[point.id];
        if (link) {
            // Returning false is this bundle's drilldown gate
            // (plotly_<type>click): it also suppresses the downstream
            // plotly_click, so the fetch lives here.
            htmx.ajax("GET", link, { target: "#reporting-region", swap: "innerHTML", push: link });
            return false;
        }
    });
};

const renderCharts = (root) => {
    root.querySelectorAll("[data-chart]").forEach(renderChart);
    // Share bars: the template carries the permille share as data; CSS paints it.
    root.querySelectorAll(".statistics-share[data-share]").forEach((bar) => {
        bar.style.setProperty("--share", bar.dataset.share);
    });
};

// The band's chip row is server-rendered out of band with every region
// response (reporting_region.html swaps #statistics-active-filters) — no
// client-side copy step.

// Out-of-order region responses are htmx's job now: the band form carries
// hx-sync="this:replace" — a new request aborts the in-flight one, so the
// last-issued request's state is always what renders. The old hand-rolled
// sequence guard lived here; it never fired (its beforeRequest matcher
// tested the swap target, but the event targets the requesting element).

// The tab nav needs no JS: the tab buttons are submit buttons of the band
// form (form="filter-toolbar-form"), so the browser serializes the clicked
// button's name/value pair into the request — the view's last-value read
// makes the click win over the hidden fallback input. The region response
// re-renders the nav out of band with the server-owned aria-current.

document.addEventListener("htmx:afterSettle", (event) => {
    renderCharts(event.target);
    makeHeadersActionable(event.target);
});

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => renderCharts(document));
} else {
    renderCharts(document);
}

// Exact-value tables sort client-side: click (or Enter/Space on) a column
// header. Interaction is delegated to the document, so tables htmx swaps in
// are sortable without re-initialisation; only header affordances (tabindex,
// title) are applied per swap. The "Other" fold row aggregates the tail and
// stays last under any order; ties keep the server's spend-led ranking
// (Array.sort is stable).
const SORTABLE_TABLE = "table.statistics-values";

const cellValue = (cell) => {
    // Value cells annotate their number with a delta span; the raw sort key
    // rides in data-sort so the annotation never pollutes the comparison.
    if (cell.dataset?.sort !== undefined && cell.dataset.sort !== "") {
        const explicit = Number(cell.dataset.sort);
        return Number.isNaN(explicit) ? cell.dataset.sort : explicit;
    }
    const text = (cell.textContent || "").replace(/\s+/g, " ").trim();
    if (text === "—" || text === "") {
        return 0; // paid out nothing sorts as zero
    }
    const numeric = Number(text.replace(/[€,\s]/g, ""));
    return Number.isNaN(numeric) ? text : numeric;
};

const sortRows = (table, columnIndex, ascending) => {
    // Only the first tbody sorts. The collapsed tail lives in a second
    // tbody below it, in the server's rank order by design. Expanding moves
    // the tail into the first tbody, so the unveiled values sort with the
    // rest. The Other fold row stays last under any order
    // (statistics-aggregate pin).
    const body = table.tBodies[0];
    const folds = [...body.rows].filter((row) => row.classList.contains("statistics-aggregate"));
    const entities = [...body.rows].filter((row) => !folds.includes(row));
    entities.sort((left, right) => {
        const a = cellValue(left.cells[columnIndex]);
        const b = cellValue(right.cells[columnIndex]);
        const order =
            typeof a === "number" && typeof b === "number"
                ? a - b
                : String(a).localeCompare(String(b));
        return ascending ? order : -order;
    });
    for (const row of entities.concat(folds)) {
        body.appendChild(row);
    }
};

const sortByHeader = (header) => {
    const table = header.closest(SORTABLE_TABLE);
    const index = header.cellIndex;
    const isFirstClick = table.dataset.sortColumn !== String(index);
    // Value columns (numbers) invite largest-first; the label column A→Z.
    const ascending = isFirstClick ? index === 0 : table.dataset.sortDirection === "descending";
    table.dataset.sortColumn = String(index);
    table.dataset.sortDirection = ascending ? "ascending" : "descending";
    table.querySelectorAll("thead th").forEach((th) => {
        th.setAttribute("aria-sort", th === header ? (ascending ? "ascending" : "descending") : "none");
    });
    sortRows(table, index, ascending);
};

const actionableHeader = (target) =>
    target instanceof Element ? target.closest(`${SORTABLE_TABLE} thead th`) : null;

document.addEventListener("click", (event) => {
    const header = actionableHeader(event.target);
    if (header) {
        sortByHeader(header);
        return;
    }
    const toggle = foldToggle(event.target);
    if (toggle) {
        toggleFold(toggle);
    }
});

// The "Other" fold row hides the tail values in a second, hidden tbody.
// Expanding moves the tail rows into the main tbody, so the unveiled values
// sort with the rest. Collapsing restores the Other row and the server's
// rank order via the rows' server indices. The expand control lives in the
// Other row's label cell, the collapse control in the tfoot (never sorted),
// and both mirror aria-expanded. They are plain link-styled anchors with
// tabindex="0": no role="button" (Pico renders that as a filled button) and
// no href (not natively key-activatable, hence the Enter/Space handler
// below). Delegated like the sorting, so htmx-swapped tables work as is.
const foldToggle = (target) =>
    target instanceof Element ? target.closest("a.statistics-fold-toggle") : null;

const toggleFold = (button) => {
    const table = button.closest("table");
    const mainBody = table.tBodies[0];
    const foldedBody = table.tBodies[1];
    if (!foldedBody) {
        return;
    }
    const otherRow = mainBody.querySelector("tr.statistics-aggregate");
    const expanded = button.getAttribute("aria-expanded") === "true";
    const byServerOrder = (left, right) =>
        Number(left.dataset.serverIndex) - Number(right.dataset.serverIndex);
    if (expanded) {
        const foldedRows = [...mainBody.rows]
            .filter((row) => row.classList.contains("statistics-folded"))
            .sort(byServerOrder);
        for (const row of foldedRows) {
            row.classList.remove("statistics-folded");
            foldedBody.append(row);
        }
        if (otherRow) {
            otherRow.hidden = false;
        }
        // Undo any client-side sort: the table returns to the server's rank
        // order (the tail kept its indices from the expand step). The sort
        // state goes too: otherwise assistive tech announces a sort that is
        // no longer applied, and the next header click flips from the stale
        // direction instead of the fresh-state default.
        for (const row of [...mainBody.rows].sort(byServerOrder)) {
            mainBody.append(row);
        }
        delete table.dataset.sortColumn;
        delete table.dataset.sortDirection;
        table
            .querySelectorAll("thead th")
            .forEach((th) => th.removeAttribute("aria-sort"));
    } else {
        // The Other row is last in the main tbody; the tail's server indices
        // continue after the visible rows, the Other row's after the tail.
        const base = mainBody.rows.length - 1;
        [...mainBody.rows].forEach((row, index) => {
            row.dataset.serverIndex = String(index);
        });
        if (otherRow) {
            otherRow.dataset.serverIndex = String(base + foldedBody.rows.length);
        }
        let index = base;
        for (const row of [...foldedBody.rows]) {
            row.dataset.serverIndex = String(index++);
            row.classList.add("statistics-folded");
            if (otherRow) {
                otherRow.before(row);
            } else {
                mainBody.append(row);
            }
        }
        if (otherRow) {
            otherRow.hidden = true;
        }
    }
    table.querySelectorAll("a.statistics-fold-toggle").forEach((toggle) => {
        toggle.setAttribute("aria-expanded", String(!expanded));
    });
    const collapseRow = table.querySelector("tr.statistics-collapse-row");
    if (collapseRow) {
        collapseRow.hidden = expanded;
    }
};

document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
        return;
    }
    const toggle = foldToggle(event.target);
    if (toggle) {
        event.preventDefault();
        toggleFold(toggle);
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
        return;
    }
    const header = actionableHeader(event.target);
    if (header) {
        event.preventDefault();
        sortByHeader(header);
    }
});

function makeHeadersActionable(root) {
    const headers =
        root instanceof HTMLTableElement
            ? root.querySelectorAll("thead th")
            : root.querySelectorAll(`${SORTABLE_TABLE} thead th`);
    // No role="button" — it would override the native columnheader role
    // (a11y.md #2) and pull in Pico's blue button background. tabindex plus
    // the Enter/Space keydown handler and aria-sort are the whole pattern.
    headers.forEach((header) => {
        header.tabIndex = 0;
        header.title = "Sort by this column";
    });
}

makeHeadersActionable(document);
