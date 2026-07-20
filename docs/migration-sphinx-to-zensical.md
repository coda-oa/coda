# Migration Plan: Sphinx → Zensical

> **Date:** 2026-07-20
> **Goal:** Replace Sphinx with [Zensical](https://zensical.org/) (v0.0.51+) as the documentation static-site generator, applying CODA brand styling.
> **Status:** Theming approach verified against [Zensical Colors docs](https://zensical.org/docs/setup/colors/) and [Customization docs](https://zensical.org/docs/customization/) — CSS variable names, custom scheme selectors, palette toggle config, and `extra_css` inclusion are all correct.

---

## 1. Current State Audit

### Sphinx configuration (`docs/conf.py`)

| Setting | Value |
|---------|-------|
| Parser | `myst_parser` (MyST Markdown) |
| Theme | `pydata_sphinx_theme` |
| Extensions | `myst_parser`, `sphinx_copybutton` |
| Custom templates | `docs/_templates/index.html` (custom landing page) |
| Static assets | `docs/_static/` — 3 CSS files, 1 HTML template, ~60 images, pico.min.css |
| Build | `make html` via `docs/Makefile` |
| Dependencies | `sphinx`, `myst-parser`, `pydata-sphinx-theme`, `sphinx-autobuild`, `sphinx-copybutton` |

### Content inventory (`docs/` — 23 Markdown files)

```
docs/
├── index.md                          # Sphinx toctree routing
├── users/
│   ├── index.md                      # Sphinx toctree routing
│   ├── about.md
│   ├── installation.md               # Uses {code-block} directive
│   ├── updating.md
│   ├── usercreation.md
│   └── features/
│       ├── index.md                  # Sphinx toctree routing
│       ├── blocklist.md
│       ├── contracts.md
│       ├── creditors.md
│       ├── csv-export.md
│       ├── funders.md
│       ├── fundingrequests.md
│       ├── fundingsources.md
│       ├── institutions.md
│       ├── invoices.md
│       ├── journals.md
│       ├── preferences.md
│       ├── publishers.md
│       ├── reporting.md
│       └── vocabularies.md
├── dev/
│   └── index.md                      # Placeholder ("Coming soon...")
├── roadmap/
│   ├── index.md                      # Sphinx toctree routing
│   └── roadmap.md
└── superpowers/
    └── specs/
        └── 2026-06-25-import-scenarios-refinement.md
```

**Sphinx/MyST-specific syntax found in content:**
- `{toctree}` directives in `index.md` files (4 occurrences)
- `{code-block}` directives in `installation.md` (1 or more)
- Image references: `![](/_static/img/...)` (many occurrences)

### CODA brand colors (`src/coda/apps/static/css/vars.css`)

| Token | Light mode | Dark mode |
|-------|-----------|-----------|
| Primary | `hsl(216, 60%, 45%)` | `hsl(218, 85%, 65%)` |
| Primary hover | `hsl(216, 60%, 35%)` | `hsl(218, 85%, 80%)` |
| Primary background | `rgb(40, 80, 150)` | — |
| Primary bg hover | `rgb(50, 90, 160)` | — |
| Secondary bg | `hsl(240, 10%, 40%)` | — |
| Background | Pico default | `rgb(13, 13, 13)` |
| Card bg | Pico default | `rgb(18, 18, 18)` |
| Text contrast | `black` | `white` |
| Accent gold (docs banner) | `hsl(40, 100%, 45%)` | — |

---

## 2. Migration Phases

### Phase 1: Install & Configure Zensical

**Steps:**

1. Add Zensical to project dependencies:
   ```toml
   # pyproject.toml
   [project.optional-dependencies]
   docs = [
     "zensical>=0.0.51",
   ]
   ```

2. Create `zensical.toml` (or `mkdocs.yml`) at project root:
   ```toml
   # zensical.toml
   [project]
   site_name = "CODA"
   site_description = "Open Access Management & Monitoring"
   site_url = "https://coda-oa.github.io/coda/"
   repo_url = "https://github.com/coda-oa/coda"
   site_author = "Sven Marcus & Linda Achilles"
   copyright = "{year}, TU Braunschweig"
   docs_dir = "docs"
   extra_css = ["assets/stylesheets/extra.css"]

   [project.theme]
   name = "material"  # Zensical's default theme (Material for MkDocs compatible)
   custom_dir = "overrides"
   logo = "assets/images/coda-logo.svg"

   [[project.theme.palette]]
   scheme = "coda"
   primary = "custom"
   accent = "custom"
   toggle.icon = "lucide/sun"
   toggle.name = "Switch to dark mode"

   [[project.theme.palette]]
   scheme = "coda-dark"
   primary = "custom"
   accent = "custom"
   toggle.icon = "lucide/moon"
   toggle.name = "Switch to light mode"

   [project.theme.font]
   text = "Montserrat"
   code = "Montserrat"
   ```

3. Define the `nav` structure (replacing toctrees):
   ```toml
   # zensical.toml
   [project.nav]
   Home = "index.md"
   "User Docs" = {
     "About" = "users/about.md",
     "Setup" = "users/installation.md",
     "Updating" = "users/updating.md",
     "User Creation" = "users/usercreation.md",
     Features = [
       { Blocklist = "users/features/blocklist.md" },
       { Contracts = "users/features/contracts.md" },
       { Creditors = "users/features/creditors.md" },
       { "CSV Export" = "users/features/csv-export.md" },
       { Funders = "users/features/funders.md" },
       { "Funding Requests" = "users/features/fundingrequests.md" },
       { "Funding Sources" = "users/features/fundingsources.md" },
       { Institutions = "users/features/institutions.md" },
       { Invoices = "users/features/invoices.md" },
       { Journals = "users/features/journals.md" },
       { Preferences = "users/features/preferences.md" },
       { Publishers = "users/features/publishers.md" },
       { Reporting = "users/features/reporting.md" },
       { Vocabularies = "users/features/vocabularies.md" },
     ]
   }
   "Developer Docs" = "dev/index.md"
   Roadmap = "roadmap/roadmap.md"
   ```

---

### Phase 2: CODA Theming

Create the custom color scheme and CODA branding as an additional stylesheet.

#### 2a. Create `docs/assets/stylesheets/extra.css`

```css
/* ==============================================
   CODA Theme for Zensical
   Maps CODA brand colors to Zensical CSS variables
   ============================================== */

/* -- Light scheme -- */
[data-md-color-scheme="coda"] {
  /* Primary: hsl(216, 60%, 45%) */
  --md-primary-fg-color:        hsl(216, 60%, 45%);
  --md-primary-fg-color--light: hsl(216, 60%, 55%);
  --md-primary-fg-color--dark:  hsl(216, 60%, 35%);

  /* Accent: coda gold */
  --md-accent-fg-color:                hsl(40, 100%, 45%);
  --md-accent-fg-color--transparent:   hsla(40, 100%, 45%, 0.1);

  /* Backgrounds */
  --md-default-bg-color:       #ffffff;
  --md-default-fg-color:       #000000;
  --md-typeset-color:          #000000;
  --md-footer-bg-color:        hsl(216, 16%, 95%);
  --md-footer-fg-color:        #000000;
}

/* -- Dark scheme -- */
[data-md-color-scheme="coda-dark"] {
  /* Primary: hsl(218, 85%, 65%) */
  --md-primary-fg-color:        hsl(218, 85%, 65%);
  --md-primary-fg-color--light: hsl(218, 85%, 75%);
  --md-primary-fg-color--dark:  hsl(218, 85%, 55%);

  /* Accent: brighter gold for dark bg */
  --md-accent-fg-color:                hsl(40, 100%, 55%);
  --md-accent-fg-color--transparent:   hsla(40, 100%, 55%, 0.15);

  /* Backgrounds (matches app dark mode) */
  --md-default-bg-color:       rgb(13, 13, 13);
  --md-default-fg-color:       #c2c7d0;
  --md-typeset-color:          #c2c7d0;

  /* Code bg similar to app's form-element background */
  --md-code-bg-color:         rgb(24, 24, 24);
  --md-code-fg-color:         #c2c7d0;

  /* Footer */
  --md-footer-bg-color:       rgb(18, 18, 18);
  --md-footer-fg-color:       #c2c7d0;
}

/* -- CODA-specific tweaks -- */
/* Banner / heading accent (gold) */
.coda-banner__title,
.coda-banner__subtitle {
  color: hsl(40, 100%, 45%);
  font-family: "Montserrat", sans-serif;
  font-weight: 300;
}

/* Footer styling */
.md-footer {
  border-top: 1px solid var(--coda-muted-border-color, #ccc);
}

/* Code block styling to match CODA form elements */
.md-typeset code {
  border-radius: var(--md-border-radius, 4px);
}
```

#### 2b. Port the custom landing page

The current `docs/_templates/index.html` uses Jinja2 (Sphinx). Zensical uses **MiniJinja** (Rust-based, Jinja2-like). The template will need rework.

1. Create `overrides/main.html` for block overrides
2. Create a custom landing page template, or override `content` block to include the CODA banner + feature grid on the homepage

Key difference: Zensical templates use `{% block name %}` / `{{ super() }}` the same way, but some template tags/filters may differ. The landing page should preserve:
- CODA banner with "CODA" title and "Open Access Management & Monitoring" subtitle
- Feature grid cards (Learn more, Funding Requests, Invoices, Reporting)
- "Get in touch" section with Matrix link
- GitHub link with SVG icon

#### 2c. Port image assets

| Current path | New path |
|---|---|
| `docs/_static/img/*` | `docs/assets/images/*` |
| `docs/_static/vars.css` | → merged into `docs/assets/stylesheets/extra.css` |
| `docs/_static/custom.css` | → merged into `docs/assets/stylesheets/extra.css` |
| `docs/_static/index.css` | → merged into landing page override |
| `docs/_static/pico.min.css` | No longer needed (Zensical has its own base styles) |

**Image path updates in Markdown:** All `![](/_static/img/...)` references must be updated to `![](../assets/images/...)` (relative to each file).

---

### Phase 3: Migrate Content

| Sphinx/MyST feature | Zensical replacement |
|---|---|
| `{toctree}` directives | Remove entirely; navigation defined in `zensical.toml` nav config |
| `{code-block} bash` / `{code-block}` | Replace with standard fenced code blocks ` ```bash ` |
| `![](_static/img/...)` | Replace with `![](assets/images/...)` (relative to `docs/`) |
| `:maxdepth:` / `:caption:` in toctrees | Not needed; handled by nav config |
| Page-level metadata in MyST frontmatter | Zensical supports YAML frontmatter natively |

File-by-file migration pattern:

1. **`docs/index.md`** — Remove toctree; use frontmatter to set a custom template:
   ```yaml
   ---
   template: home.html
   ---
   ```
   Content can remain minimal since the home page is a custom template.

2. **`docs/users/index.md`** — Remove toctree; convert to a simple overview page or delete if navigation handles it.

3. **`docs/users/features/index.md`** — Same as above.

4. **`docs/roadmap/index.md`** — Same as above (or delete, since roadmap.md is linked directly in nav).

5. **`docs/users/installation.md`** — Replace `{code-block}` directives with standard fenced code blocks:
   ````diff
   - ```{code-block} bash
   + ```bash
   git clone https://github.com/coda-oa/coda
   ```
   ````

6. **All files** — Update image paths:
   `![](/_static/img/...)` → `![](../assets/images/...)`

---

### Phase 4: Build System & Dependencies

#### Update `pyproject.toml`

```diff
 [project.optional-dependencies]
 docs = [
-  "sphinx>=8.0.2",
-  "myst-parser>=4.0.0",
-  "pydata-sphinx-theme>=0.15.4",
-  "sphinx-autobuild>=2024.4.16",
-  "sphinx-copybutton>=0.5.2",
+  "zensical>=0.0.51",
 ]
```

#### Replace build commands

| Sphinx | Zensical |
|---|---|
| `make html` (in `docs/`) | `zensical build` (from project root) |
| `make serve` / `python -m http.server 8200` | `zensical preview` |
| — | `zensical new` (init new project) |

Add PDM scripts for convenience:
```toml
[tool.pdm.scripts]
docs-build = "zensical build"
docs-preview = "zensical preview"
docs-clean = "rm -rf site/"
```

#### Remove Sphinx artifacts

Delete the following files and directories:
- `docs/conf.py`
- `docs/Makefile`
- `docs/make.bat`
- `docs/_templates/` (contents ported to `overrides/`)
- `docs/_static/` (assets ported to `docs/assets/`)

---

### Phase 5: Deployment

The site currently deploys to GitHub Pages at `https://coda-oa.github.io/coda/`. After migration:

1. Build: `zensical build` → outputs to `site/` (default)
2. Deploy using `ghp-import` or a GitHub Action:
   ```yaml
   # .github/workflows/docs.yml (create if needed)
   name: Deploy docs
   on:
     push:
       branches: [main]
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - run: pip install zensical
         - run: zensical build
         - uses: peaceiris/actions-gh-pages@v3
           with:
             github_token: ${{ secrets.GITHUB_TOKEN }}
             publish_dir: ./site
   ```

---

### Phase 6: Validation Checklist

- [ ] `zensical build` completes without errors
- [ ] All 23+ pages render correctly
- [ ] Navigation matches previous structure
- [ ] Landing page (banner + feature grid) matches original design
- [ ] All ~60 images load with correct paths
- [ ] Code blocks render with syntax highlighting
- [ ] Dark/light mode toggle works
- [ ] Dark mode colors match CODA app dark theme
- [ ] Light mode colors match CODA app light theme
- [ ] Internal links between pages work
- [ ] External links (Matrix, GitHub, etc.) work
- [ ] Font (Montserrat) loads correctly
- [ ] Responsive layout (mobile/tablet/desktop)
- [ ] Search functionality works

---

## 3. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Zensical is alpha software (v0.0.51) | Medium | Pin exact version; test thoroughly before merging |
| MiniJinja vs Jinja2 template differences | Medium | Review and test each template override; skip complex overrides initially |
| Image path changes across 23 files | Low | Use `sed` or script for bulk replacement |
| {code-block} directives missed | Low | grep for remaining MyST syntax after migration |
| Navigation re-ordering mismatches | Low | Validate nav matches original toctree order exactly |

---

## 4. Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|-------------|
| Install & Configure | 30 min | None |
| CODA Theming | 2–3 hrs | Brand colors audited |
| Port landing page | 2–3 hrs | Theming complete |
| Migrate content (23 files) | 2–4 hrs | Image paths updated |
| Build system & deps | 30 min | Content migrated |
| Deployment | 30 min | Build verified |
| Validation | 1–2 hrs | All phases complete |
| **Total** | **~8–14 hrs** | — |

---

## 5. Rollback Plan

If issues arise after deployment:

1. **Revert `pyproject.toml`** — restore the `[project.optional-dependencies] docs` section
2. **Restore deleted files** — `conf.py`, `Makefile`, `make.bat`, `_templates/`, `_static/`
3. **Revert image paths** — `git checkout -- docs/` for all modified Markdown files
4. **Delete** `zensical.toml`, `overrides/`, `docs/assets/`, `site/`

All changes should be made on a dedicated branch for easy rollback.
