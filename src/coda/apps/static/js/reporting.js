// Renders the server-built plotly figures of the statistics page (plan §9).
// Each [data-chart] mount names the json_script carrying the figure — the exact
// {data, layout, config} object Plotly.newPlot consumes. No inline JS, no
// escaping work here: the template owns the payloads, this file only paints.
// Runs on first load and after every htmx swap of the statistics region, so a
// filter change re-paints the freshly swapped charts.

// Commit-on-blur for the band form's date fields and search box. The band
// form once carried this as `focusout changed[...]` in hx-trigger, but htmx
// only reads a bracket filter directly after the event name — the filter sat
// after `changed`, was dropped with a syntax error per token, and the bare
// `focusout changed` fired on every first blur of every field in the form.
// And htmx's `changed` seeds its last-value map with the *listener* element
// (the form), so no hx-trigger spelling of "changed since focus" exists;
// tracking the per-field value in JS is the only faithful form. The search
// box has no input debounce on this page (the pipeline is too expensive for
// search-as-you-type), so blur is its only commit besides Enter.
//
// focusout (unlike blur) bubbles, and the form is never htmx-swapped, so one
// delegated listener on the form survives the period block's OOB re-renders.
const COMMIT_ON_BLUR = ".filter-search, #id_start_date, #id_end_date";
const bandForm = document.getElementById("filter-toolbar-form");
if (bandForm) {
    const lastCommitted = new WeakMap();
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
    // A submit serializes the fields' current values, so anything the submit
    // carried is committed as far as the blur path is concerned. Without the
    // re-seed, "type into search + Enter, then blur" fires a second, identical
    // request: the blur dispatches change, the trigger's 300ms delay queues it
    // behind the submit via hx-sync, and it still runs after the swap.
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

const renderChart = (element) => {
    const source = document.getElementById(element.dataset.chart);
    if (!source || element.dataset.plotlyRendered === "true") {
        return;
    }
    const figure = JSON.parse(source.textContent);
    const config = { responsive: true, ...figure.config };
    element.dataset.plotlyRendered = "true";
    Plotly.newPlot(element, figure.data, figure.layout, config);
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
