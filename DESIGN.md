# ElfieNest Console Design System

## 1. Atmosphere & Identity

ElfieNest Console feels like a quiet local operations room for embodied agents: clear, trustworthy, and slightly alive without looking theatrical. The signature is a soft technical habitat, where structured management surfaces sit beside a calm creature preview and privacy-aware detail states.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/base | --surface-base | #F6F8F7 | #101513 | App background |
| Surface/primary | --surface-primary | #FFFFFF | #171D1A | Main panels |
| Surface/secondary | --surface-secondary | #EEF3F0 | #202822 | Sidebar, quiet bands |
| Surface/elevated | --surface-elevated | #FFFFFF | #232B26 | Popovers, modals |
| Surface/inset | --surface-inset | #E8EFEB | #151B18 | Inputs, preview wells |
| Text/primary | --text-primary | #17211D | #F4F8F5 | Main content |
| Text/secondary | --text-secondary | #617069 | #BAC7C0 | Supporting copy |
| Text/tertiary | --text-tertiary | #87938D | #83918A | Muted metadata |
| Border/default | --border-default | #DCE5DF | #314038 | Card outlines |
| Border/subtle | --border-subtle | #EDF2EF | #25312C | Dividers |
| Accent/primary | --accent-primary | #177A63 | #4AC29A | Primary actions, focus |
| Accent/hover | --accent-hover | #0F5F4E | #7CDAB8 | Primary hover |
| Accent/soft | --accent-soft | #DDF3EA | #173A31 | Selected states |
| Accent/amber | --accent-amber | #8C6D1F | #E2BD4F | Warnings, adoption highlights |
| Accent/indigo | --accent-indigo | #445C8A | #8EA8DE | LLM and system markers |
| Status/success | --status-success | #2E7D57 | #70D69B | Healthy states |
| Status/warning | --status-warning | #A1661B | #E5B86D | Cautions |
| Status/error | --status-error | #B94A48 | #F19A98 | Errors |
| Status/info | --status-info | #3B6F80 | #86C5D4 | Informational states |

### Rules

- Large surfaces use neutral tokens. Accents appear only for state, hierarchy, and interaction.
- Admin-only visibility uses `--accent-indigo`; ownership and adoption use `--accent-primary`.
- Raw color values are only defined in this document and CSS token declarations.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| H1 | 32px | 700 | 1.25 | 0 | Page titles |
| H2 | 24px | 650 | 1.3 | 0 | Section headers |
| H3 | 18px | 650 | 1.35 | 0 | Panel and card titles |
| Body/lg | 16px | 450 | 1.65 | 0 | Lead descriptions |
| Body | 14px | 450 | 1.6 | 0 | Default UI text |
| Body/sm | 13px | 450 | 1.5 | 0 | Secondary rows and metadata |
| Caption | 12px | 600 | 1.45 | 0 | Tags, labels, counters |
| Micro | 11px | 650 | 1.35 | 0 | Tiny state labels |

### Font Stack

- Primary: "Avenir Next", "SF Pro Display", "Helvetica Neue", Arial, sans-serif
- Mono: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace

### Rules

- Body text never drops below 13px in functional controls.
- Page headings stay compact because this is an operational console, not a landing page.
- Letter spacing is always 0.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a base of 4px.

| Token | Value | Usage |
|-------|-------|-------|
| --space-1 | 4px | Tight joins |
| --space-2 | 8px | Icon gaps, compact controls |
| --space-3 | 12px | Input padding, list rhythm |
| --space-4 | 16px | Default panel padding |
| --space-5 | 20px | Group spacing |
| --space-6 | 24px | Card padding |
| --space-8 | 32px | Major panel gaps |
| --space-10 | 40px | Page section rhythm |
| --space-12 | 48px | Wide workspace margins |

### Grid

- App shell: fixed sidebar plus fluid workspace.
- Max content width: none; dashboard tools use the full viewport responsibly.
- Breakpoints: mobile below 760px, tablet 760px to 1100px, desktop above 1100px.

### Rules

- Management content is dense but scan-friendly. No decorative page cards inside other cards.
- Fixed-format controls use stable dimensions to prevent layout shifts.
- Mobile collapses the sidebar into a top navigation band.

## 5. Components

### App Shell

- **Structure**: sidebar, topbar, main workspace, optional right detail drawer.
- **Variants**: admin, user.
- **Spacing**: `--space-4`, `--space-6`, `--space-8`.
- **States**: active navigation, hidden admin menus for user role.
- **Accessibility**: landmarks for navigation and main content.
- **Motion**: panel changes fade and translate over standard timing.

### Segmented Control

- **Structure**: button group inside a quiet surface.
- **Variants**: role switch, elf filters, wizard steps.
- **Spacing**: `--space-1`, `--space-2`, `--space-3`.
- **States**: selected, hover, focus, disabled.
- **Accessibility**: buttons expose pressed state.
- **Motion**: background and transform only.

### Elf Card

- **Structure**: status bar, name block, tags, metrics, action row.
- **Variants**: owned, other user, pending request.
- **Spacing**: `--space-4`, `--space-5`.
- **States**: hover, selected, privacy-limited.
- **Accessibility**: card action is a button with clear label.
- **Motion**: subtle transform on hover.

### Drawer Panel

- **Structure**: header, permission callout, content regions, footer actions.
- **Variants**: owner detail, admin limited detail, profile editor, adoption wizard.
- **Spacing**: `--space-5`, `--space-6`.
- **States**: open, closing, loading, error, empty.
- **Accessibility**: focusable close button and labelled sections.
- **Motion**: translate and opacity only.

### Config Section

- **Structure**: labelled field groups, provider cards, documentation block.
- **Variants**: LLM, room, advanced, docs.
- **Spacing**: `--space-4`, `--space-6`.
- **States**: enabled, disabled, warning, saved.
- **Accessibility**: fields have labels and descriptions.
- **Motion**: no decorative motion.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Button press, toggle |
| Standard | 220ms | ease-in-out | Drawer, tab, card selection |
| Emphasis | 420ms | cubic-bezier(0.16, 1, 0.3, 1) | Wizard preview reveal |

### Rules

- Animate only `transform`, `opacity`, and `filter`.
- All interactive controls have hover, active, focus-visible, and disabled states.
- `prefers-reduced-motion` disables non-essential transitions.

## 7. Depth & Surface

### Strategy

Mixed, but restrained: borders define structure, tonal shifts define hierarchy, and shadows appear only for overlays.

| Level | Value | Usage |
|-------|-------|-------|
| Border/default | 1px solid var(--border-default) | Cards, panels, inputs |
| Border/subtle | 1px solid var(--border-subtle) | Dividers, rows |
| Shadow/overlay | 0 24px 70px rgba(23, 33, 29, 0.14) | Drawers, menus |
| Shadow/card | 0 10px 28px rgba(23, 33, 29, 0.06) | Hovered cards only |

