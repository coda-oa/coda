(function () {
  "use strict";

  const layout = document.querySelector(".filter-layout");
  const toggle = document.getElementById("filter-drawer-toggle");
  const dialog = layout?.querySelector("#filter-sidebar");
  if (!layout || !toggle || !dialog) {
    return;
  }

  const narrowViewport = window.matchMedia("(width < 1400px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let restoreToggleAfterClose = false;
  let isClosing = false;

  // Suppress the blur change event when input already scheduled this search value.
  const searchInput = layout.querySelector(".filter-search");
  searchInput?.addEventListener("input", () => {
    searchInput.dataset.lastInputValue = searchInput.value;
  });

  const updateModalState = () => {
    const isModal = dialog.matches(":modal");
    document.body.classList.toggle("filter-drawer-open", isModal);
    toggle.setAttribute("aria-expanded", String(isModal));
  };

  const focusFirstVisibleDescendant = () => {
    const candidates = dialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
        'select:not([disabled]), textarea:not([disabled]), ' +
        'search-select:not([disabled]), search-select-multi:not([disabled]), ' +
        '[tabindex]:not([tabindex="-1"])',
    );
    for (const candidate of candidates) {
      const style = getComputedStyle(candidate);
      if (
        candidate.getClientRects().length === 0 ||
        style.visibility === "hidden" ||
        style.opacity === "0"
      ) {
        continue;
      }
      candidate.focus();
      if (dialog.contains(document.activeElement)) {
        return;
      }
    }
  };

  const finishModalClose = () => {
    if (!isClosing) {
      return;
    }
    isClosing = false;
    dialog.removeEventListener("transitionend", finishModalCloseTransition);
    dialog.close();
    dialog.classList.remove("filter-sidebar-closing");
    updateModalState();
  };

  const finishModalCloseTransition = (event) => {
    if (event.target === dialog && event.propertyName === "transform") {
      finishModalClose();
    }
  };

  const cancelModalClose = () => {
    if (!isClosing) {
      return;
    }
    isClosing = false;
    dialog.removeEventListener("transitionend", finishModalCloseTransition);
    dialog.classList.remove("filter-sidebar-closing");
  };

  const closeModalForUser = () => {
    if (!dialog.matches(":modal") || isClosing) {
      return;
    }
    restoreToggleAfterClose = true;
    if (reducedMotion.matches) {
      dialog.close();
      updateModalState();
      return;
    }
    isClosing = true;
    dialog.addEventListener("transitionend", finishModalCloseTransition);
    dialog.classList.add("filter-sidebar-closing");
  };

  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeModalForUser();
  });
  dialog.addEventListener("close", () => {
    updateModalState();
    if (restoreToggleAfterClose) {
      restoreToggleAfterClose = false;
      toggle.focus();
    }
  });
  reducedMotion.addEventListener("change", (event) => {
    if (event.matches && isClosing) {
      finishModalClose();
    }
  });

  // The template starts open for the desktop modeless rail.
  if (narrowViewport.matches && dialog.open && !dialog.matches(":modal")) {
    dialog.close();
  }
  updateModalState();

  toggle.addEventListener("click", () => {
    if (!narrowViewport.matches) {
      return;
    }
    if (dialog.matches(":modal")) {
      closeModalForUser();
      return;
    }
    restoreToggleAfterClose = false;
    if (dialog.open) {
      cancelModalClose();
      dialog.close();
    }
    dialog.showModal();
    updateModalState();
  });

  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog || !dialog.matches(":modal")) {
      return;
    }
    const bounds = dialog.getBoundingClientRect();
    if (
      event.clientX < bounds.left ||
      event.clientX > bounds.right ||
      event.clientY < bounds.top ||
      event.clientY > bounds.bottom
    ) {
      closeModalForUser();
    }
  });

  // Delegated: the × close button lives inside the OOB-swapped drawer
  // header, so its DOM node is replaced after every filter change.
  layout.addEventListener("click", (event) => {
    if (
      event.target instanceof Element &&
      event.target.closest("#filter-drawer-close")
    ) {
      closeModalForUser();
    }
  });

  narrowViewport.addEventListener("change", (event) => {
    const activeElement = document.activeElement;
    if (event.matches) {
      const focusWasInDialog = dialog.contains(activeElement);
      cancelModalClose();
      restoreToggleAfterClose = false;
      if (dialog.open) {
        dialog.close();
      }
      updateModalState();
      if (focusWasInDialog) {
        toggle.focus();
      }
      return;
    }

    const shouldMoveFocus = dialog.contains(activeElement) || activeElement === toggle;
    cancelModalClose();
    restoreToggleAfterClose = false;
    if (dialog.matches(":modal")) {
      dialog.close();
    }
    if (!dialog.open) {
      dialog.show();
    }
    updateModalState();
    if (shouldMoveFocus) {
      focusFirstVisibleDescendant();
    }
  });
})();
