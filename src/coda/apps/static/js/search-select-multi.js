const TEMPLATE = document.createElement('template');
TEMPLATE.innerHTML =  /*html*/ `
    <style>
        :host {
            line-height: var(--coda-line-height);
            font-size: var(--coda-font-size);
            display: block;
        }

        .container {
            position: relative;
            max-width: 100%;
            width: 100%;
        }

        .container > * {
            box-sizing: border-box;
            line-height: var(--coda-line-height);
            font-size: 1rem;
        }

        .search-input {
            width: 100%;
            padding: var(--coda-form-element-spacing-vertical) var(--coda-form-element-spacing-horizontal);
            border: 1px solid var(--coda-border-color);
            border-radius: var(--coda-border-radius);
            background-color: var(--coda-form-element-background-color);
            height: calc(1rem* var(--coda-line-height) + var(--coda-form-element-spacing-vertical)* 2 + var(--coda-border-width)* 2);
        }

        .search-input::placeholder {
            color: #8891a4;
        }

        .search-input:has( + .selected-options:not(:empty)) {
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
        }

        .dropdown {
            display: none;
            position: absolute;
            top: 100%;
            left: 0;

            z-index: 99;

            border: 1px solid var(--coda-border-color);
            border-radius: var(--coda-border-radius);
            width: 100%;
            max-height: calc(1rem * var(--coda-line-height, 1.5) * 20);
            overflow-y: auto;

            padding: calc(var(--coda-spacing) / 2);

            background-color: var(--coda-card-background-color);
        }

        .dropdown.active {
            display: block;
        }

        .option {
            border-radius: var(--coda-border-radius);
            padding: var(--coda-form-element-spacing-vertical) var(--coda-form-element-spacing-horizontal);
            cursor: pointer;
        }

        .option:hover {
            background-color: var(--coda-secondary-background);
            color: var(--coda-secondary-inverse);
        }

        .selected-options {
            display: flex;
            overflow-x: auto;
            gap: calc(var(--coda-gap) / 2);
        }

        .selected-options:not(:empty) {
            margin-bottom: 0.5rem;
            padding: calc(var(--coda-spacing) / 2);
            border: 1px solid var(--coda-border-color);
            border-top: none;
            border-bottom-left-radius: var(--coda-border-radius);
            border-bottom-right-radius: var(--coda-border-radius);
        }

        .selected-tag {
            background-color: var(--coda-secondary-background);
            color: var(--coda-secondary-inverse);
            padding: 0.125rem 0.5rem;
            border-radius: var(--coda-border-radius);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.25rem;
        }

        .selected-tag span {
            text-wrap: none;
            white-space: nowrap;
        }

        .remove-btn {
            font-size: calc(var(--coda-font-size) * 1.1);
            cursor: pointer;
            border: none;
            background: none;
            color: var(--coda-text-contrast-color);
        }
    </style>
    <div class="container">
        <input type="text" part="search-input" class="search-input">
        <div class="selected-options"></div>
        <div class="dropdown">
            <slot name="options"></slot>
        </div>
    </div>
`;

class SearchSelectMulti extends HTMLElement {
    static formAssociated = true;

    constructor() {
        super();
        this.options = [];
        this._queuedQuery = null;
        this.selectedOptions = new Map();
        this.slotOptions = [];
        this.attachShadow({ mode: 'open' });
        this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
        this.internals = this.attachInternals();
    }

    connectedCallback() {
        this.setupListeners();
        this.loadOptionsFromSlot();
        this.restoreRemoteSearchState();
    }

    restoreRemoteSearchState() {
        if (!this.hasAttribute('remote-search')) {
            return;
        }
        const input = this.shadowRoot.querySelector('.search-input');
        const rendered = this.getAttribute('data-q') || '';
        input.value = rendered;
        // The term is seeded from the markup on every (re)connect — the only
        // state that outlives a swap is what the server rendered.
        this._queuedQuery = rendered || null;
        // The OOB rail swap recreated this element while the search box had
        // the caret; the fetching element marked its name so focus returns.
        if (window.__facetSearchFocused === this.getAttribute('name')) {
            window.__facetSearchFocused = null;
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }
    }

    setupListeners() {
        const input = this.shadowRoot.querySelector('.search-input');
        const dropdown = this.shadowRoot.querySelector('.dropdown');

        input.addEventListener('input', () => {
            // Real typing is what the search tracks; selection clears the
            // visible box, but the term must survive that (see syncRemoteQuery).
            this._queuedQuery = input.value;
            this.handleSearch(input.value);
            this.queueRemoteSearch(input.value);
        });
        input.addEventListener('focus', () => this.showDropdown());
        input.addEventListener('click', () => this.showDropdown());
        input.addEventListener('blur', (e) => this.handleBlur(e, dropdown));
        dropdown.addEventListener('mousedown', (e) => this.handleDropdownMouseDown(e));
    }

    queueRemoteSearch(query) {
        if (!this.hasAttribute('remote-search')) {
            return;
        }
        clearTimeout(this._remoteTimer);
        this._remoteTimer = setTimeout(() => {
            const hidden = this._remoteInput();
            if (!hidden || hidden.value === query) {
                return;
            }
            hidden.value = query;
            window.__facetSearchFocused = this.getAttribute('name');
            this.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
        }, 300);
    }

    disconnectedCallback() {
        clearTimeout(this._remoteTimer);
    }

    _remoteInput() {
        return this.querySelector(`input[type="hidden"][name="${this.getAttribute('name')}_q"]`);
    }

    syncRemoteQuery() {
        // The hidden input can never lag what the user searched. The tracked
        // value is the queued *typing*, not the visible field: selectOption
        // empties the box before dispatching its change, and a selection must
        // not drop the term — the rail stays narrowed so another value under
        // the same term can be picked without retyping. The element dies with
        // each swap and the fresh one restores the term from data-q.
        if (!this.hasAttribute('remote-search')) {
            return;
        }
        clearTimeout(this._remoteTimer);
        const hidden = this._remoteInput();
        if (hidden) {
            hidden.value = this._queuedQuery ?? '';
        }
    }

    handleSearch(query) {
        const filteredOptions = this.filterOptions(query);
        const slotOptions = this.getSlotOptions(query);
        const uniqueOptions = [...new Set([...filteredOptions, ...slotOptions])];
        this.updateDropdown(uniqueOptions);
    }

    filterOptions(query) {
        return this.options.filter(option =>
            option.toLowerCase().includes(query.toLowerCase()) &&
            !Array.from(this.selectedOptions.keys()).includes(option)
        );
    }

    getSlotOptions(query) {
        return this.slotOptions.filter(optionElement =>
            optionElement.textContent.trim().toLowerCase().includes(query.toLowerCase())
        ).map(optionElement => optionElement.textContent.trim());
    }

    optionEntry(optionElement, optionText) {
        return { text: optionText, color: optionElement.dataset.color || null };
    }

    selectOption(optionText) {
        const optionElement = this.slotOptions.find(option => option.textContent.trim() === optionText);
        if (optionElement && optionElement.value) {
            const optionValue = optionElement.value;
            this.selectedOptions.set(optionValue, this.optionEntry(optionElement, optionText));
            this.updateSelectedOptions();
            this.updateOriginalOptionElement(optionValue, true);
            this.updateFormValue();
            this.clearSearchInput();
            this.hideDropdown();
            this.dispatchChangeEvent();
        }
    }

    removeSelectedOption(optionValue) {
        this.selectedOptions.delete(optionValue);
        this.updateSelectedOptions();
        this.updateOriginalOptionElement(optionValue, false);
        this.updateFormValue();
        this.dispatchChangeEvent();
    }

    updateOriginalOptionElement(optionValue, isSelected) {
        this.slotOptions.forEach(optionElement => {
            if (optionElement.value === optionValue) {
                if (isSelected) {
                    optionElement.setAttribute('selected', '');
                } else {
                    optionElement.removeAttribute('selected');
                }
            }
        });
    }

    updateSelectedOptions() {
        const container = this.shadowRoot.querySelector('.selected-options');
        container.innerHTML = Array.from(this.selectedOptions.entries())
            .map(([value, { text, color }]) => this.createSelectedTag(value, text, color))
            .join('');

        container.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', () => this.removeSelectedOption(btn.dataset.option));
        });
        this.syncPlaceholder();
    }

    syncPlaceholder() {
        const placeholder = this.getAttribute('placeholder');
        if (!placeholder) {
            return;
        }
        const input = this.shadowRoot.querySelector('.search-input');
        input.placeholder = this.selectedOptions.size > 0 ? '' : placeholder;
    }

    createSelectedTag(value, text, color) {
        const style = color
            ? ` style="background-color: color-mix(in hsl, ${color} 25%, transparent 75%); border: 1px solid ${color}; color: var(--coda-text-contrast-color)"`
            : '';
        return `
            <div class="selected-tag"${style}>
                <span>${text}</span>
                <button class="remove-btn" data-option="${value}">×</button>
            </div>
        `;
    }

    loadOptionsFromSlot() {
        const slot = this.shadowRoot.querySelector('slot[name="options"]');
        if (slot) {
            this.slotOptions = slot.assignedNodes().filter(node => node.nodeType === Node.ELEMENT_NODE);
            this.slotOptions.forEach(optionElement => {
                const optionText = optionElement.textContent.trim();
                const optionValue = optionElement.value;
                this.options.push(optionText);
                if (optionElement.hasAttribute('selected')) {
                    this.selectedOptions.set(optionValue, this.optionEntry(optionElement, optionText));
                }
            });
            this.updateDropdown(this.options);
            this.updateSelectedOptions();
            // Hydrated selections must reach the form value here: the swap that
            // created this element may already have run formAssociatedCallback
            // with an empty selection, and that ordering is engine-specific.
            this.updateFormValue();
        }
    }

    showSlotOptions() {
        this.updateDropdown(this.slotOptions.map(optionElement => optionElement.textContent.trim()));
    }

    updateDropdown(options) {
        const dropdown = this.shadowRoot.querySelector('.dropdown');
        dropdown.innerHTML = options.length > 0
            ? options.map(option => `<div class="option">${option.trim()}</div>`).join('')
            : '<div class="option no-select">No options found</div>';

        dropdown.querySelectorAll('.option').forEach(option => {
            if (!option.classList.contains('no-select')) {
                option.addEventListener('click', () => this.selectOption(option.textContent));
            }
        });
    }

    clearSearchInput() {
        this.shadowRoot.querySelector('.search-input').value = '';
        this.updateDropdown(this.options);
    }

    hideDropdown() {
        this.shadowRoot.querySelector('.dropdown').classList.remove('active');
    }

    showDropdown() {
        const dropdown = this.shadowRoot.querySelector('.dropdown');
        dropdown.classList.add('active');
        this.showSlotOptions();
    }

    handleBlur(e, dropdown) {
        if (!dropdown.contains(e.relatedTarget)) {
            dropdown.classList.remove('active');
        }
    }

    handleDropdownMouseDown(e) {
        e.preventDefault(); // Prevent blur event
        if (e.target.classList.contains('option')) {
            this.selectOption(e.target.textContent);
        }
    }

    dispatchChangeEvent() {
        this.syncRemoteQuery();
        this.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
    }

    updateFormValue() {
        const value = Array.from(this.selectedOptions.keys());
        const formData = new FormData();
        value.forEach(v => formData.append(this.getAttribute('name'), v));
        this.internals.setFormValue(formData);
        if (this.hasAttribute('required') && this.selectedOptions.size === 0) {
            this.internals.setValidity({ valueMissing: true }, 'Please select at least one option.', this.shadowRoot.querySelector('.search-input'));
        } else {
            this.internals.setValidity({});
        }
    }

    checkValidity() {
        this.updateFormValue();
        return this.internals.checkValidity();
    }

    reportValidity() {
        this.updateFormValue();
        return this.internals.reportValidity();
    }

    setCustomValidity(message) {
        this.internals.setValidity({ customError: !!message }, message, this.shadowRoot.querySelector('.search-input'));
    }

    formAssociatedCallback() {
        this.updateFormValue();
    }
}

customElements.define('search-select-multi', SearchSelectMulti);

// A failed region fetch means no swap and no reconnect would consume the
// focus marker; drop it so the next unrelated swap cannot steal focus.
const clearFacetSearchFocus = () => {
    window.__facetSearchFocused = null;
};
document.addEventListener('htmx:responseError', clearFacetSearchFocus);
document.addEventListener('htmx:sendError', clearFacetSearchFocus);
