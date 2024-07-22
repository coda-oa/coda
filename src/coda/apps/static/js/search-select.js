'use strict';

import {
    addGlobalStylesToShadowRoot
} from "./global-styles.js"

const htmlTemplate = /*html*/ `
<div class="search-select">
    <input type="text" id="search-box" autocomplete="off" required>
    <ul id="search-results" class="no-decoration">
        <slot>
    </ul>
</div>

<style>
    .search-select {
        position: relative;
    }

    #search-results {
        position: absolute;
        width: 100%;
        z-index: 99;

        margin-block: calc(-1 * var(--coda-spacing));
        padding: calc(var(--coda-spacing) / 2);

        border: 1px solid var(--coda-muted-border-color);
        border-radius: var(--coda-border-radius);
        background-color: var(--coda-card-background-color);

        visibility: hidden;
        opacity: 0;
        transition: visibility 0s, opacity 0.2s linear;

        & ::slotted(li) {
            padding-inline: calc(var(--coda-spacing) / 2);
            padding-block: calc(var(--coda-spacing) / 2);
            border-radius: var(--coda-border-radius);
        }

        & ::slotted(li:hover),
        & ::slotted(li:focus),
        & ::slotted(li.focus) {
            background-color: var(--coda-secondary-background);
        }
    }

    #search-results:hover,
    #search-results.visible:focus-within {
        visibility: visible;
        opacity: 1;
    }

    #search-results.visible {
        visibility: visible;
        opacity: 1;
    }
</style>
`


class SearchSelect extends HTMLElement {
    static formAssociated = true

    constructor() {
        super()
        this._internals = this.attachInternals()

        this.attachShadow({
            mode: "open"
        })
        const template = document.createElement("template")
        template.innerHTML = htmlTemplate
        this.shadowRoot.appendChild(template.content.cloneNode(template))
        addGlobalStylesToShadowRoot(this.shadowRoot)
    }

    connectedCallback() {
        this._currentIndex = -1
        this.searchBox = this.shadowRoot.querySelector(".search-select > #search-box")
        this.value = this.searchBox.value
        this._slot = this.shadowRoot.querySelector("slot")
        this._slot.addEventListener("slotchange", () => {
            this.listItems = this._slot.assignedElements()
            this.validOptions = this.listItems.map(li => li.getAttribute("value"))
            Array.from(this.listItems).forEach(li => this.assignLiClickHandler(li))
        })

        this.searchBox.addEventListener("keyup", (e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                const direction = e.key === "ArrowDown" ? 1 : -1;
                this.navigateListItems(direction)
            } else if (e.key === "Enter") {
                this.setValueToActiveElementOrFirstVisible();
                this.searchBox.focus()
                this.searchResults.classList.remove("visible")
            } else if (e.key === "Escape") {
                this.searchBox.blur()
            } else {
                this.searchResults.classList.add("visible")
                this.filterListItems()
                this.value = this.searchBox.value
            }
        })

        this.searchResults = this.shadowRoot.querySelector("#search-results")
        this.searchBox.addEventListener("focus", () => {
            this.searchResults.classList.add("visible")
            this.filterListItems()
        })

        this.searchBox.addEventListener("blur", () => {
            this.searchResults.classList.remove("visible")
        })

        this.searchBox.addEventListener("change", () => {
            this.filterListItems()
            this.value = this.searchBox.value
        })

    }

    setValueToActiveElementOrFirstVisible() {
        if (this.activeElement) {
            this.value = this.activeElement.getAttribute("value");
        } else {
            this.value = this.visibleItems?.[0]?.getAttribute("value");
            this.searchBox.value = this.visibleItems?.[0]?.innerText;
        }
    }

    assignLiClickHandler(li) {
        li.addEventListener("click", () => {
            this.searchBox.value = li.innerText;
            this.value = li.getAttribute("value");
            this.searchBox.focus();
            this.searchResults.classList.remove("visible");
        });
    }

    navigateListItems(direction) {
        if (this.visibleItems?.length === 0) {
            return
        }

        const iter = new DoubleSidedIterator(this.visibleItems, this._currentIndex, direction)
        const curentElement = iter.current()
        curentElement?.classList.remove("focus")
        this.activeElement = iter.next()
        this.activeElement.classList.add("focus");
        this._currentIndex = iter.index()
        this.searchBox.value = this.activeElement.innerText;
        this.value = this.activeElement.getAttribute("value");
    }

    filterListItems() {
        const searchTerm = this.searchBox.value;
        const arr = Array.from(this.listItems);
        arr.filter((li) => li.style.display !== "none" && !this.matches(searchTerm, li))
            .forEach(li => li.style.display = "none")

        arr.filter(li => li.style.display === "none" && this.matches(searchTerm, li))
            .forEach(li => li.style.display = "list-item")

        this.visibleItems = arr.filter(li => li.style.display !== "none")
    }

    matches(searchTerm, li) {
        return searchTerm.length == 0 || li.innerText.includes(searchTerm);
    }

    set value(value) {
        this._internals.setFormValue(value)
        this._value = value
        this.updateValidity()
    }

    updateValidity() {
        let validity, message;
        if (!this.isValidSelection()) {
            validity = {
                badInput: true
            };
            message = `${this.value} is not a valid option`;
        } else {
            validity = this.searchBox.validity;
            message = this.searchBox.validationMessage;
        }
        this._internals.setValidity(validity, message, this.searchBox)
    }

    isValidSelection() {
        return this.validOptions?.includes(this.value);
    }

    checkValidity() {
        return this._internals.checkValidity()
    }

    reportValidity() {
        return this._internals.reportValidity()
    }

    get validity() {
        return this._internals.validity
    }

    get value() {
        return this._value
    }


    get form() {
        return this._internals.form
    }

    get name() {
        return this.getAttribute("name")
    }

    get type() {
        return this.localName
    }
}


class DoubleSidedIterator {
    constructor(array, start, direction = 1) {
        this._array = array
        this._index = start
        this._direction = direction
    }

    index() {
        return this._index
    }

    current() {
        return this._array[this._index]
    }

    next() {
        this._index = this.normalizeIndex(this._index + this._direction, this._array)
        if (this._index >= this._array.length) {
            this._index = 0
        }
        return this._array[this._index]
    }

    previous() {
        this._index = this.normalizeIndex(this._index - this._direction, this._array)
        if (this._index < 0) {
            this._index = this._array.length - 1
        }
        return this._array[this._index]
    }
    normalizeIndex(index, listItems) {
        if (index < 0) {
            return listItems.length - 1
        }
        if (index >= listItems.length) {
            return 0
        }
        return index
    }
}

customElements.define("search-select", SearchSelect)
