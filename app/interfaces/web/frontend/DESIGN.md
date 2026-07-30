# ElfieNest Web Design System

## 1. Atmosphere & Identity

ElfieNest is a warm, calm owner console: paper-like surfaces, a restrained
earth-tone accent, and dense-but-readable operational information. Its signature
is a quiet "nest ledger" material—soft warm fields with clear, tactile controls,
not a generic SaaS dashboard.

## 2. Color

The active palette is selected with `:root[data-theme]`. `warm-paper` is the
default; `harbor-blue`, `orchid-archive`, and `moss-green` provide equivalent
semantic palettes. Components must use semantic tokens, never a page-local color.

| Role | Existing token | shadcn semantic token | Usage |
| --- | --- | --- | --- |
| Canvas | `--page-bg` | `--background` | Page background |
| Raised surface | `--surface-raised` | `--card`, `--popover` | Cards and dialogs |
| Field surface | `--surface-field` | `--secondary` | Inputs and secondary controls |
| Primary ink | `--text` | `--foreground` | Main text |
| Muted ink | `--text-muted` | `--muted-foreground` | Labels and metadata |
| Brand action | `--accent` | `--primary` | Primary action and checked state |
| Subtle action | `--surface-hover` | `--accent` | Hovered and quiet actions |
| Divider | `--border` | `--border`, `--input` | Boundaries and inputs |
| Keyboard focus | `--focus-ring` | `--ring` | Focus indicator |
| Error | `--error-text` | `--destructive` | Destructive actions and errors |

## 3. Typography

The application uses `Noto Serif SC`, `Songti SC`, and serif fallbacks for its
editorial character; monospace is reserved for JSON and machine values. Use
12px only for non-essential captions, 14px for labels and supporting text, 16px
for body and identity values, 18px for card titles, 22px for section headings,
and a responsive 32–48px display scale. Operational card labels must never drop
below 14px. All visible operational text inside management cards, field rows,
status labels, table cells, and sidebar actions has a 14px floor; only decorative
captions or non-operational metadata may use 12px. Numeric fields use tabular
figures where alignment matters.

## 4. Spacing & Layout

The base unit is 4px. Common spacing is 4, 8, 12, 16, 20, 24, 32, 40, 48, and
64px. Product shells use the `fixed-sidenav-shell` primitive: the side navigation
is fixed inside the viewport-height workbench, and the main pane is the only
primary scroll owner. The sidebar may scroll only its own navigation list when
the list exceeds the rail height. Responsive grids collapse to one readable
column at 760px or below; controls may wrap but must never create
primary-content horizontal scrolling.

## 5. Components

### shadcn Button
- **Structure:** native button through the generated shadcn primitive.
- **Variants:** default, secondary, outline, ghost, destructive, icon-only.
- **States:** hover, pressed, focus-visible, disabled, loading.
- **Accessibility:** semantic button, keyboard activation, visible ring.
- **Sizing:** the application default is 40px high with 16px horizontal
  padding; compact and icon-only sizes are reserved for dense toolbars.
- **Color:** primary hover keeps light text on the darker brand surface.
  Outline controls use the field surface and strong border at rest so they
  remain recognizable as buttons; outline and ghost hover use the quiet
  surface with normal foreground text.
- **Action hierarchy:** page-level reload actions always use the filled primary
  button with a leading refresh icon. Outline is reserved for cancel, inspect,
  verify, and other lower-priority choices.

### shadcn Input and number stepper
- **Structure:** generated input inside a single bordered control group for
  decrement, editable value, and increment.
- **States:** default, hover, focus-within, invalid, disabled.
- **Accessibility:** labelled input, descriptive text, disabled bounds.
- **Anatomy:** a number stepper is one 40px bordered shell with square internal
  dividers. Its buttons and input never render separate outer borders or radii.

### Field Row
- **Structure:** visible settings and form fields use a label-left,
  control-right row at every width. The label column keeps the field name and
  optional help text; the control column owns inputs, selects, toggles, and
  validation feedback.
- **Responsive behavior:** true product fields stay label-left/control-right at
  desktop, tablet, and 375px mobile widths; the 760px breakpoint must not stack
  the label above the control. Long labels, CJK text, values, and validation
  feedback wrap inside their own columns without clipping or horizontal page
  overflow.
- **Accessibility:** the visible label, help, invalid state, and control stay
  programmatically associated.

### shadcn Checkbox and grouped Select
- **Structure:** generated Radix-backed primitives supplied by shadcn.
- **States:** default, hover, checked/selected, focus-visible, disabled.
- **Accessibility:** label association, keyboard selection, portal-safe focus.
- **Grouped Select:** option sets with categories use labelled Select groups and
  separators, not repeated standalone selects or ad-hoc native dropdowns.

### shadcn Dialog and Alert Dialog
- **Structure:** generated Radix-backed overlay, content, heading, description,
  and action area.
- **States:** open, close, cancel, confirm, pending.
- **Accessibility:** focus trap, labelled title/description, opener focus return.

### shadcn Table
- **Structure:** tabular data uses the shadcn Table primitive for header, body,
  row, head, and cell anatomy.
- **States:** default, hover row, selected row when applicable, empty, loading,
  and error.
- **Accessibility:** native table semantics, header associations, 14px minimum
  operational text, and no pseudo-table grids for new table work.

### Management Sidebar
- **Structure:** fixed side navigation with the logo and a single `ELFIE NEST`
  brand label. Console subtitles such as `OWNER CONSOLE` are not shown in the
  rail.
- **Sizing:** every navigation, quick-action, and compact account target is
  exactly 48px tall on desktop and compact rails. The active route keeps
  `aria-current="page"`.
- **Grouping:** navigation groups use semantic group labels; visual group titles
  and dividers stay tight so the rail reads as one control surface.
- **States:** default, hover, focus-visible, active, and pressed all use existing
  semantic tokens only.

### Observation Monitor Toolbar
- **Structure:** one compact horizontal reel overlays the 3D surface; commands
  never wrap or create a second control row.
- **Scrolling:** the reel keeps native horizontal input while rendering a 4px
  visual scrollbar with a transparent track and semantic divider-colored thumb.
- **Icon semantics:** Owner monitor entry points and the toolbar overview command
  use the Lucide `Cctv` icon. Generic camera preview actions may retain `Camera`.
- **States:** default, hover, focus-visible, pressed camera, paused, hidden, and
  restored.

### Identity Card
- **Structure:** a reusable shadcn Card shell with one fixed square portrait on
  the left and a horizontal `label：value` grid on the right.
- **Sizing:** 104px square portrait on desktop, 64px square on narrow screens;
  user and Elfie cards share the same portrait geometry and type ramp.
- **Typography:** 14px labels and 16px values; long IDs and descriptions may
  span the full information grid without returning to stacked title/content.
- **Status:** availability and lifecycle states render as semantic dot plus text
  pairs; a dot alone is not sufficient status communication.
- **Inline edit:** simple identity edits stay inline inside the card or account
  panel, with the display value replaced by its labelled control and save/cancel
  affordance in the same row. Dialogs are reserved for multi-field or destructive
  decisions.

### Personal dossier
- **Reference priority:** the profile dossier follows
  `.omo/evidence/elfie-profile-ui-redo/references/elfie-lab-profile-primary.png`
  for portrait/identity, stage dominance, and radar composition. The private
  module rhythm follows `elfie-lab-private-modules.png`. These references define
  geometry and hierarchy only; product colors continue to come from semantic
  theme tokens.
- **Shell and scroll owner:** the dossier fills the available chat detail pane
  with no fixed dossier max-width. The detail pane remains bounded by the
  fixed-sidenav/list-detail shell, and the dossier body is the vertical scroll
  owner. Internal sections do not introduce nested vertical scroll except chart
  detail dialogs.
- **Identity geometry:** desktop uses portrait-left/identity-right anatomy with
  a direct chat action aligned to the header action edge. Mobile at 760px or
  below keeps the portrait and identity in a compact two-column header, then
  stacks sections into one readable column with a mobile back action outside the
  desktop header hierarchy.
- **Stage primitive:** `profile-dossier__stage` is the dominant media frame. On
  desktop its width follows the detail pane and its aspect ratio must remain
  landscape, 1.5-1.8. On mobile it becomes compact at 0.9-1.2. The stage uses
  theme field/raised/divider/focus tokens, never page-local green or screenshot
  color literals.
- **Sections and actions:** section headers use a small semantic label, a
  22-26px title, and a compact action cluster. Controls must be keyboard
  reachable, 44px or taller on touch breakpoints, and preserve visible
  `--focus-ring` outlines.
- **Radar and chart text alternatives:** Big Five is public and read-only.
  Radar/graph canvases are always paired with a semantic value list or edge
  summary that communicates the same meaning without color, position, or canvas
  access.
- **Private modules:** adopter-only modules use divider-led accordion rows:
  plain section dividers, chevron state, `aria-expanded`, and bodies mounted
  only when open. Visitors receive no private headings, placeholder locks, or
  hidden private copy in the DOM.
- **Motion and adaptive states:** direct-manipulation stage motion is purposeful
  and GPU-composited. Under `prefers-reduced-motion`, transitions are reduced to
  state changes without decorative movement. Long CJK copy, empty data, missing
  portraits, theme switching, and 200% zoom must not create horizontal page
  overflow.

## 6. Motion & Interaction

Controls transition color, border, shadow, opacity, and transform for 140–200ms
with `ease-out`; pressed controls may use a small transform only. Respect
`prefers-reduced-motion`; no decorative motion is required.

## 7. Depth & Surface

Use mixed depth: a quiet one-pixel tinted border for cards and inputs, tonal
separation for nested controls, and the existing tinted floating shadow only for
dialogs and menus. Avoid heavy shadows and rounded-pill treatment by default.

## 8. Accessibility Constraints & Accepted Debt

Target WCAG 2.2 AA: all controls have a visible focus ring, keyboard operation,
and text contrast appropriate to the active theme. Current accepted debt: legacy
native or pseudo-table surfaces for model, food, and runtime catalog data remain
until their scoped shadcn Table migration tasks; no accepted sidebar, field-row,
status, or identity-card visual debt.

## 9. Bilingual Interface Contract

The bilingual interface extends the existing warm-paper design language; it does
not introduce a second layout, palette, or component set for English. Both
`zh-CN` and `en-US` use the same semantic tokens, spacing scale, information
architecture, and responsive shells.

### Language Switcher

- **Anatomy:** use one shared labelled `LanguageSwitcher`, built from the
  existing `SelectField` and shadcn/Radix Select primitives. It has one visible
  label, one trigger, and a portal listbox with exactly two self-named options:
  `简体中文` and `English`.
- **Placement:** login, setup, and the account menu may place the shared control
  in their existing action areas. Placement must not change navigation hierarchy
  or create a page-specific language state.
- **States:** default, hover, focus-visible, expanded, selected, and disabled
  use existing semantic tokens. The current option remains selected when the
  list opens; changing locale keeps the trigger focused and does not reset URL,
  scroll, form, dialog, or application state.
- **Keyboard:** Tab reaches the trigger in document order; Enter or Space opens
  it; Arrow keys move between options; Enter commits; Escape closes without a
  change; Tab closes and advances. The trigger and portal items retain a visible
  `--focus-ring`, and the accessible name is localized with the surrounding UI.

### Script, Metadata, and Text Expansion

- `--font-sans` remains the single UI typography owner. Its fallback chain must
  cover Latin through `Noto Serif` or the Latin glyphs in `Noto Serif SC`, CJK
  through `Noto Serif SC` and `Songti SC`, then generic `serif`. Components must
  not introduce language-specific local font stacks; monospace remains reserved
  for machine values.
- The document root is the metadata authority. It is updated synchronously to
  `lang="zh-CN"` or `lang="en-US"`; both supported locales use `dir="ltr"`.
  Portals inherit the active document language and direction. A component must
  not infer locale from rendered text or own a competing `lang` state.
- English UI copy must be designed for at least 30% expansion over the Chinese
  label. Buttons and field rows may grow or wrap; use `min-width: 0`, intrinsic
  sizing, and natural line wrapping instead of fixed widths derived from CJK
  copy. Operational labels and instructions may not be ellipsized when that
  would hide an action or required meaning.
- User content, IDs, model/provider names, JSON, and other machine values are not
  translated. They wrap within their owning region without changing the
  bilingual UI typography contract.

### Responsive and Accessibility Acceptance

- Validate both locales at 375px, 768px, and 1280px. Also validate reflow at
  200% zoom at narrow and desktop widths. Locale changes must not cause clipped
  controls, overlapping text, hidden focus indicators, or lost keyboard focus.
- The document and primary product shell must never acquire horizontal page
  scrolling. Long English and CJK text wrap inside the existing grid/flex owner;
  children that can shrink use `min-width: 0`. Purpose-built local scrollers,
  such as the monitor toolbar or a data table, remain locally bounded and do not
  make `html`, `body`, or the application root wider than the viewport.
- Keyboard-only acceptance covers opening and committing the language switch,
  cancelling it with Escape, continuing with Tab, and operating the surrounding
  page after the locale changes. Focus order, focus return, and visible
  focus-visible styling must be equivalent in both languages.
