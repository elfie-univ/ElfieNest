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
