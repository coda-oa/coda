window.ConceptListUI = (() => {
    function toggleButtonState(checkboxName, buttonId) {
        const checkboxes = document.querySelectorAll(`input[name="${checkboxName}"]`);
        const button = document.getElementById(buttonId);

        function update() {
            const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
            if (button) button.disabled = !anyChecked;
        }

        checkboxes.forEach(cb => cb.addEventListener('change', update));
        update();
    }

    function setupSelectDeselectButtons(checkboxName, selectBtnId, deselectBtnId) {
        const checkboxes = document.querySelectorAll(`input[name="${checkboxName}"]`);
        const selectBtn = document.getElementById(selectBtnId);
        const deselectBtn = document.getElementById(deselectBtnId);

        if (selectBtn) {
            selectBtn.addEventListener('click', () => {
                checkboxes.forEach(cb => {
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change'));
                });
                updateDeselectState();
            });
        }

        if (deselectBtn) {
            deselectBtn.addEventListener('click', () => {
                checkboxes.forEach(cb => {
                    cb.checked = false;
                    cb.dispatchEvent(new Event('change'));
                });
                updateDeselectState();
            });
        }


        function updateDeselectState() {
            if (!deselectBtn) return;
            const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
            deselectBtn.disabled = !anyChecked;
        }

        checkboxes.forEach(cb => cb.addEventListener('change', updateDeselectState));
        updateDeselectState();
    }

    function setupFilter(inputId, checkboxContainerSelector) {
        const input = document.getElementById(inputId);
        const container = document.querySelector(checkboxContainerSelector);

        if (!input || !container) return;

        input.addEventListener('input', () => {
            const search = input.value.toLowerCase();
            const items = container.querySelectorAll('li');

            items.forEach(item => {
                const labelText = item.textContent.toLowerCase();
                item.style.display = labelText.includes(search) ? '' : 'none';
            });
        });
    }

    return {
        toggleButtonState,
        setupSelectDeselectButtons,
        setupFilter
    };
})();
function initializeConceptUI() {
    ConceptListUI.toggleButtonState("disallow", "disallow-button");
    ConceptListUI.toggleButtonState("allow", "allow-button");

    ConceptListUI.setupSelectDeselectButtons("disallow", "select-all-allowed", "deselect-all-allowed");
    ConceptListUI.setupSelectDeselectButtons("allow", "select-all-forbidden", "deselect-all-forbidden");

    ConceptListUI.setupFilter("allowed-filter", "#allowed-checkboxes");
    ConceptListUI.setupFilter("forbidden-filter", "#forbidden-checkboxes");
}


document.addEventListener("DOMContentLoaded", initializeConceptUI);


document.body.addEventListener("htmx:afterSwap", initializeConceptUI);
