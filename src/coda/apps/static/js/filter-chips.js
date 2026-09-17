(function () {
    "use strict";

    // Every region response re-renders the whole sidebar from the URL, so the
    // server's markup is the widget state after a × click — no client-side
    // reset is needed. What is left is the flash affordance on the chip body.
    document.addEventListener("click", (event) => {
        if (event.target.closest(".active-filter-remove")) {
            return; // the × is a plain htmx GET; its response re-renders the controls
        }

        // Clicking a chip (not its × link) scrolls to and flashes the control
        // that holds the value, e.g. "approved" -> Processing Status.
        const chip = event.target.closest(".active-filter");
        if (!chip) {
            return;
        }
        const target = document.getElementById(chip.dataset.source);
        if (!target) {
            return;
        }
        target.classList.remove("filter-flash");
        // Force reflow so re-adding the class restarts the animation.
        void target.offsetWidth;
        target.classList.add("filter-flash");
        // Timeout rather than animationend: the class must clear even when the
        // animation never ticks (background tabs, reduced motion).
        if (target._filterFlashTimer) {
            window.clearTimeout(target._filterFlashTimer);
        }
        target._filterFlashTimer = window.setTimeout(() => {
            target.classList.remove("filter-flash");
            target._filterFlashTimer = undefined;
        }, 1300);
    });
})();
