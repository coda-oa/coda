(function () {
    "use strict";

    // Clicking an active-filter chip (not its × link) scrolls to and flashes
    // the control that holds the value, e.g. "approved" -> Processing Status.
    document.addEventListener("click", (event) => {
        const chip = event.target.closest(".active-filter");
        if (!chip || event.target.closest(".active-filter-remove")) {
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
