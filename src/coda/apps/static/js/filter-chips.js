(function () {
    "use strict";

    // Return a control to the sidebar's unfiltered default state.
    // Conventions: a select's default is the option with an empty value; a
    // radio group's (segment) default is its first option; text/date inputs
    // and switch checkboxes default to empty/unchecked; custom selects
    // (search-select / search-select-multi) drop their selection.
    function resetControl(el) {
        if (!el) {
            return;
        }
        const tag = el.tagName;
        if (tag === "SELECT") {
            if (Array.from(el.options).some((option) => option.value === "")) {
                el.value = "";
            }
        } else if (tag === "INPUT") {
            if (el.type === "radio") {
                const group = el.form
                    ? Array.from(
                          el.form.querySelectorAll(
                              `input[type="radio"][name="${CSS.escape(el.name)}"]`,
                          ),
                      )
                    : [el];
                group.forEach((radio) => {
                    radio.checked = false;
                });
                if (group[0]) {
                    group[0].checked = true;
                }
            } else if (el.type === "checkbox") {
                el.checked = false;
                if (el.hasAttribute("aria-checked")) {
                    el.setAttribute("aria-checked", "false");
                }
            } else {
                el.value = "";
            }
        } else if (tag === "SEARCH-SELECT") {
            resetSearchSelect(el);
        } else if (tag === "SEARCH-SELECT-MULTI") {
            Array.from(el.selectedOptions.keys()).forEach((value) =>
                el.removeSelectedOption(value),
            );
        }
    }

    function resetSearchSelect(el) {
        const items = el.listItems || [];
        const blank = items.find((li) => li.getAttribute("value") === "");
        items.forEach((li) => {
            li.removeAttribute("selected");
        });
        if (blank) {
            blank.setAttribute("selected", "");
        }
        el._currentIndex = items.indexOf(blank);
        el.value = "";
        el.searchBox.value = blank ? blank.textContent.trim() : "";
        el.resetFilter();
    }

    document.addEventListener("click", (event) => {
        const remove = event.target.closest(".active-filter-remove");
        if (remove) {
            // The × both drops the value from the URL (htmx) and resets the
            // control that held it, so the sidebar reflects the new state.
            const chip = remove.closest(".active-filter");
            if (chip) {
                resetControl(document.getElementById(chip.dataset.source));
            }
            return;
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
