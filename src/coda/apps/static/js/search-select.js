'use strict';

import {
    addGlobalStylesToShadowRoot
} from "./global-styles.js"

const htmlTemplate = /*html*/ `
<div id="search-results-wrapper">
    <input type="text" id="search-box" autocomplete="off" required>
    <ul id="search-results" class="no-decoration">
        <slot>
    </ul>
</div>

<style>
    #search-box {
        display: block;
        position: relative;
        width: 100%;
    }

    #search-results-wrapper::after {
        display: block;
        width: 1rem;
        height: calc(1rem * var(--coda-line-height, 1.5));

        position: absolute;

        right: 1rem;
        top: calc(50% - .5rem);

        pointer-events: none;
        transform: rotate(0) translateX(.2rem);
        transition: transform 0.15s ease-in-out;
        background-image: var(--pico-icon-chevron);
        background-position: right center;
        background-size: 1rem auto;
        background-repeat: no-repeat;
        content: "";
    }

    #search-results-wrapper:focus-within::after {
        transform: rotate(180deg) translateX(-.2rem);
    }

    #search-results-wrapper {
        display: block;
        position: relative;
    }

    #search-results {
        position: absolute;
        width: 100%;
        max-height: calc(1rem * var(--coda-line-height, 1.5) * 20);
        overflow-y: auto;
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
            cursor: pointer;
        }

        & ::slotted(li:hover),
        & ::slotted(li:focus),
        & ::slotted(li.focus) {
            color: var(--coda-secondary-inverse);
            background-color: var(--coda-secondary-background);
        }
    }

    /*
    #search-results:hover,
    #search-results.visible:focus-within {
        visibility: visible;
        opacity: 1;
    }
    */

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
        this.searchBox = this.shadowRoot.querySelector("#search-box")
        this.searchResults = this.shadowRoot.querySelector("#search-results")
        this._slot = this.shadowRoot.querySelector("slot")

        this.value = null
        this._slot.addEventListener("slotchange", () => {
            this.listItems = this._slot.assignedElements()
            this.visibleItems = this.listItems
            this.validOptions = this.listItems.map(li => li.getAttribute("value"))
            const selected = this.listItems.find(li => li.hasAttribute("selected"))
            const index = this.listItems.indexOf(selected)
            if (selected !== undefined) {
                this.searchBox.value = selected.textContent.trim()
                this._currentIndex = index
                this.value = selected.getAttribute("value")
            }
        })

        this.searchBox.addEventListener("keyup", (e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                this.searchResults.classList.add("visible")
                const direction = e.key === "ArrowDown" ? 1 : -1
                this.navigateListItems(direction)
            } else if (e.key === "Enter") {
                this.searchBox.focus()
                this.searchResults.classList.remove("visible")
            } else if (e.key === "Escape") {
                this.searchBox.blur()
            } else {
                this.searchResults.classList.add("visible")
                this.filterListItems()
            }
        })

        this.searchResults.addEventListener("mousedown", (e) => {
            if (e.target.tagName === 'LI') {
                this.searchBox.value = e.target.textContent
                this.setActiveElement(e.target, this.visibleItems.indexOf(e.target))
                this.setValueToActiveElementOrFirstMatch()
                this.searchResults.classList.remove("visible")
            }
        })

        this.searchBox.addEventListener("blur", () => {
            this.searchResults.classList.remove("visible")
            this.resetFilter()
        })

        this.searchBox.addEventListener("focus", () => {
            this.searchBox.select()
            this.searchResults.classList.add("visible")
        })

        this.searchBox.addEventListener("change", () => {
            this.setValueToActiveElementOrFirstMatch()
            this.filterListItems()
        })

    }

    resetFilter() {
        this.listItems.forEach(li => li.style.display = "list-item")
        this.visibleItems = this.listItems
    }

    setValueToActiveElementOrFirstMatch() {
        if (this.activeElement !== undefined) {
            this.value = this.activeElement.getAttribute("value")
            this.searchBox.value = this.activeElement.textContent
        } else {
            const match = this.firstMatch()
            this.value = match?.getAttribute("value")
            this.searchBox.value = match?.textContent
        }
    }

    firstMatch() {
        return this.visibleItems.filter(li => this.matches(li))[0]
    }

    navigateListItems(direction) {
        if (this.visibleItems?.length === 0) {
            return
        }

        const iter = new DoubleSidedIterator(this.visibleItems, this._currentIndex, direction)
        this.setActiveElement(iter.next(), iter.index())
        this.setValueToActiveElementOrFirstMatch()
        this.activeElement.scrollIntoView({
            block: "nearest"
        })
    }

    filterListItems() {
        const arr = Array.from(this.listItems)
        arr.filter((li) => this.isVisible(li) && !this.matches(li))
            .forEach(li => li.style.display = "none")

        arr.filter(li => !this.isVisible(li) && this.matches(li))
            .forEach(li => li.style.display = "list-item")

        this.visibleItems = arr.filter(li => this.isVisible(li))
        if (this.visibleItems.length > 0)
            this.setActiveElement(this.visibleItems[0], 0)
    }

    setActiveElement(li, index) {
        this.activeElement?.classList.remove("focus")

        this.activeElement = li
        this.activeElement.classList.add("focus")
        this._currentIndex = index
    }

    isVisible(li) {
        return li.style.display !== "none"
    }

    matches(li) {
        const searchTerm = this.searchBox.value
        return searchTerm.length == 0 || li.textContent.includes(searchTerm)
    }

    set value(value) {
        this._internals.setFormValue(value)
        this._value = value
        this.updateValidity()
    }

    updateValidity() {
        let validity, message
        if (!this.isValidSelection()) {
            validity = {
                badInput: true
            }
            message = `${this.value} is not a valid option`
        } else {
            validity = this.searchBox.validity
            message = this.searchBox.validationMessage
        }
        this._internals.setValidity(validity, message, this.searchBox)
    }

    isValidSelection() {
        return this.validOptions?.includes(this.value)
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
        return this._array[this._index ?? 0]
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
