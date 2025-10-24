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

    function setupLevelSelection(dropdownId, buttonId, checkboxContainerSelector) {
        const dropdown = document.getElementById(dropdownId);
        const button = document.getElementById(buttonId);
        const container = document.querySelector(checkboxContainerSelector);

        if (!dropdown || !button || !container) return;

        // Function to update button state based on dropdown selections
        function updateButtonState() {
            const selectedLevels = dropdown.querySelectorAll('input[type="checkbox"]:checked');
            button.disabled = selectedLevels.length === 0;
        }

        // Listen for changes in the dropdown checkboxes
        dropdown.addEventListener('change', updateButtonState);

        // Initial state check
        updateButtonState();

        button.addEventListener('click', () => {
            // Get selected levels from dropdown
            const selectedLevels = Array.from(dropdown.querySelectorAll('input[type="checkbox"]:checked'))
                .map(cb => parseInt(cb.name.split('-')[1])); // Extract level number from "level-1", "level-2", etc.

            if (selectedLevels.length === 0) return;

            // Find and check all checkboxes at the selected levels
            const targetCheckboxes = container.querySelectorAll('input[type="checkbox"][name*="_concepts_check"]');

            targetCheckboxes.forEach(checkbox => {
                const checkboxLevel = parseInt(checkbox.getAttribute('data-level'));
                if (selectedLevels.includes(checkboxLevel)) {
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change')); // Trigger change event for UI updates
                }
            });

            // Close the dropdown and clear selections
            dropdown.removeAttribute('open');
            dropdown.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => cb.checked = false);
            updateButtonState(); // Update button state after clearing
        });
    }

    return {
        toggleButtonState,
        setupSelectDeselectButtons,
        setupFilter,
        setupLevelSelection
    };
})();
function initializeConceptUI() {
    ConceptListUI.toggleButtonState("allowed_concepts_check", "disallow-button");
    ConceptListUI.toggleButtonState("disallowed_concepts_check", "allow-button");

    ConceptListUI.setupSelectDeselectButtons("allowed_concepts_check", "select-all-allowed", "deselect-all-allowed");
    ConceptListUI.setupSelectDeselectButtons("disallowed_concepts_check", "select-all-forbidden", "deselect-all-forbidden");

    ConceptListUI.setupFilter("allowed-filter", "#allowed-checkboxes");
    ConceptListUI.setupFilter("forbidden-filter", "#forbidden-checkboxes");

    // Setup level selection functionality for both sides
    ConceptListUI.setupLevelSelection("allowed-levels-dropdown", "allowed-levels-select-button", "#allowed-checkboxes");
    ConceptListUI.setupLevelSelection("disallowed-levels-dropdown", "disallowed-levels-select-button", "#forbidden-checkboxes");
}


document.addEventListener("DOMContentLoaded", initializeConceptUI);


document.body.addEventListener("htmx:afterSwap", initializeConceptUI);
