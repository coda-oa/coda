const themeToggle = {
    init() {
        this.root = document.documentElement;
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        let theme = localStorage.getItem('theme');
        if (theme === undefined) {
            theme = prefersDark ? 'dark' : 'light';
        }
        this.theme = theme
        this.setTheme(this.theme);
        if (this.theme === 'dark') {
            document.querySelector('#theme-switch').checked = true;
        }
        this.setupListeners();
    },

    setTheme(theme) {
        this.root.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    },

    toggle() {
        const newTheme = this.root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
    },

    setupListeners() {
        const themeSwitch = document.querySelector('#theme-switch');
        themeSwitch.addEventListener('change', () => this.toggle());
    }
};

document.addEventListener('DOMContentLoaded', () => themeToggle.init());
