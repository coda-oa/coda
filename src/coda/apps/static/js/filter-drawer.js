(function () {
    "use strict";

    const layout = document.querySelector(".filter-layout");
    const toggle = document.getElementById("filter-drawer-toggle");
    if (!layout || !toggle) {
        return;
    }
    const backdrop = document.getElementById("filter-sidebar-backdrop");

    const isOpen = () => layout.classList.contains("filter-drawer-open");

    const setOpen = (open) => {
        layout.classList.toggle("filter-drawer-open", open);
        document.body.classList.toggle("filter-drawer-open", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (!open && document.activeElement?.closest(".filter-sidebar")) {
            // Closed from inside the drawer (× or Escape): give focus back to
            // the only control that can open it again.
            toggle.focus();
        }
    };

    toggle.addEventListener("click", () => {
        setOpen(!isOpen());
    });

    backdrop?.addEventListener("click", () => {
        setOpen(false);
    });

    // Delegated: the × close button lives inside the OOB-swapped drawer
    // header, so its DOM node is replaced after every filter change.
    layout.addEventListener("click", (event) => {
        if (event.target.closest("#filter-drawer-close")) {
            setOpen(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isOpen()) {
            setOpen(false);
        }
    });
})();
