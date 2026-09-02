(function () {
    "use strict";

    const layout = document.querySelector(".filter-layout");
    const toggle = document.getElementById("filter-drawer-toggle");
    if (!layout || !toggle) {
        return;
    }

    const isOpen = () => layout.classList.contains("filter-drawer-open");

    const setOpen = (open) => {
        layout.classList.toggle("filter-drawer-open", open);
        toggle.setAttribute("aria-expanded", String(open));
    };

    toggle.addEventListener("click", () => {
        setOpen(!isOpen());
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
