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
            top: calc(var(--coda-form-element-spacing-vertical) + var(--coda-line-height));
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
        }

        .selected-options {
            display: flex;
            overflow-x: auto;
            gap: calc(var(--coda-gap) / 2);
        }

        .selected-options:not(:empty) {
            margin-bottom: var(--coda-spacing);
            padding: calc(var(--coda-spacing) / 2);
            border: 1px solid var(--coda-border-color);
            border-top: none;
            border-bottom-left-radius: var(--coda-border-radius);
            border-bottom-right-radius: var(--coda-border-radius);
        }

        .selected-tag {
            background-color: var(--coda-secondary-background);
            color: var(--coda-secondary-inverse);
            padding: calc(var(--coda-spacing) / 2);
            border-radius: var(--coda-border-radius);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .selected-tag span {
            text-wrap: none;
            white-space: nowrap;
        }

        .remove-btn {
            font-size: calc(var(--coda-font-size) * 1.25);
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
        this.selectedOptions = new Map();
        this.slotOptions = [];
        this.attachShadow({ mode: 'open' });
        this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
        this.internals = this.attachInternals();
    }

    connectedCallback() {
        this.setupListeners();
        this.loadOptionsFromSlot();
    }

    setupListeners() {
        const input = this.shadowRoot.querySelector('.search-input');
        const dropdown = this.shadowRoot.querySelector('.dropdown');

        input.addEventListener('input', () => this.handleSearch(input.value));
        input.addEventListener('focus', () => this.showDropdown());
        input.addEventListener('click', () => this.showDropdown());
        input.addEventListener('blur', (e) => this.handleBlur(e, dropdown));
        dropdown.addEventListener('mousedown', (e) => this.handleDropdownMouseDown(e));
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
        }
    }

    removeSelectedOption(optionValue) {
        this.selectedOptions.delete(optionValue);
        this.updateSelectedOptions();
        this.updateOriginalOptionElement(optionValue, false);
        this.updateFormValue();
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
