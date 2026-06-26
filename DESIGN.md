# ElfieNest Management Design System

## 1. Atmosphere & Identity

ElfieNest 管理端是一个安静的本地生命体控制室：它要让安装、模型供应商、房间容量、精灵领养和运行状态都能被快速扫描，不像营销页，也不装饰过度。视觉签名是“柔和技术栖息地”：浅色操作面、细网格背景、克制绿色强调色，以及密集但清楚的配置面板。

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/base | --surface-base | #F6F8F7 | #101513 | App background |
| Surface/primary | --surface-primary | #FFFFFF | #171D1A | Primary panels |
| Surface/secondary | --surface-secondary | #EEF3F0 | #202822 | Sidebar and quiet bands |
| Surface/elevated | --surface-elevated | #FFFFFF | #232B26 | Popovers and modals |
| Surface/inset | --surface-inset | #E8EFEB | #151B18 | Inputs and data wells |
| Text/primary | --text-primary | #17211D | #F4F8F5 | Main text |
| Text/secondary | --text-secondary | #617069 | #BAC7C0 | Secondary text |
| Text/tertiary | --text-tertiary | #87938D | #83918A | Muted metadata |
| Border/default | --border-default | #DCE5DF | #314038 | Cards and inputs |
| Border/subtle | --border-subtle | #EDF2EF | #25312C | Dividers and grid lines |
| Accent/primary | --accent-primary | #177A63 | #4AC29A | Primary actions |
| Accent/hover | --accent-hover | #0F5F4E | #7CDAB8 | Primary hover |
| Accent/soft | --accent-soft | #DDF3EA | #173A31 | Selected states |
| Accent/amber | --accent-amber | #8C6D1F | #E2BD4F | Warnings and setup guidance |
| Accent/indigo | --accent-indigo | #445C8A | #8EA8DE | Model and route markers |
| Status/success | --status-success | #2E7D57 | #70D69B | Healthy states |
| Status/warning | --status-warning | #A1661B | #E5B86D | Cautions |
| Status/error | --status-error | #B94A48 | #F19A98 | Errors and destructive actions |
| Status/info | --status-info | #3B6F80 | #86C5D4 | Informational states |

### Rules

- Large surfaces stay neutral; accent colors are reserved for hierarchy, state, and commands.
- Provider and model status use semantic status tokens, never arbitrary colors.
- Raw color values should appear only in token declarations or SVG avatar palettes.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| H1 | 32px | 700 | 1.25 | 0 | Page titles |
| H2 | 24px | 650 | 1.3 | 0 | Section titles |
| H3 | 18px | 650 | 1.35 | 0 | Card and panel titles |
| Body/lg | 16px | 450 | 1.65 | 0 | Lead copy |
| Body | 14px | 450 | 1.6 | 0 | Default UI text |
| Body/sm | 13px | 450 | 1.5 | 0 | Secondary rows |
| Caption | 12px | 600 | 1.45 | 0 | Labels and badges |
| Micro | 11px | 650 | 1.35 | 0 | Tiny state labels |

### Font Stack

- Primary: "Avenir Next", "SF Pro Display", "Helvetica Neue", Arial, sans-serif
- Mono: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace

### Rules

- Body text in controls never drops below 13px.
- Page headings are compact because this is an operational console.
- Letter spacing is always 0.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a 4px base.

| Token | Value | Usage |
|-------|-------|-------|
| --space-1 | 4px | Tight joins |
| --space-2 | 8px | Icon gaps |
| --space-3 | 12px | Input padding |
| --space-4 | 16px | Panel padding |
| --space-5 | 20px | Group spacing |
| --space-6 | 24px | Card padding |
| --space-8 | 32px | Major panel gaps |
| --space-10 | 40px | Page section rhythm |
| --space-12 | 48px | Wide workspace margins |

### Grid

- App shell: fixed 272px sidebar plus fluid workspace.
- Content uses the available width for dashboards; repeated cards collapse from three columns to one column.
- Breakpoints: mobile below 760px, tablet 760px to 1100px, desktop above 1100px.

### Rules

- Operational content is dense but scan-friendly.
- Cards are limited to repeated items, framed tools, modals, and dashboards.
- Mobile uses a compact top navigation band rather than a tall desktop sidebar.

## 5. Components

### App Shell

- **Structure**: sidebar, topbar, main workspace, optional modal overlays.
- **Variants**: admin console and user workspace.
- **Spacing**: --space-4, --space-6, --space-8.
- **States**: active navigation, mobile collapsed nav, authenticated profile.
- **Accessibility**: nav and main landmarks, visible focus.
- **Motion**: panel changes use opacity and transform only.

### Metric Card

- **Structure**: label, numeric value, supporting text.
- **Variants**: healthy, warning, informational.
- **Spacing**: --space-5 and --space-6.
- **States**: loading skeleton, empty fallback.
- **Accessibility**: data is text, not decorative-only color.
- **Motion**: none.

### Data Card

- **Structure**: heading, status badge, metadata, action row.
- **Variants**: provider, model, elfie, command, setup step.
- **Spacing**: --space-4, --space-5.
- **States**: hover, active, saving, error, empty.
- **Accessibility**: actions are buttons with clear labels.
- **Motion**: hover transform only.

### Config Form

- **Structure**: labeled field groups, inline help, action footer.
- **Variants**: LLM, adoption, engine, security, provider modal.
- **Spacing**: --space-3, --space-4, --space-6.
- **States**: loading, dirty, saving, saved, error.
- **Accessibility**: every input has a label.
- **Motion**: no decorative motion.

### Modal

- **Structure**: backdrop, header, body, footer actions.
- **Variants**: provider edit, user edit, profile, password.
- **Spacing**: --space-5, --space-6.
- **States**: open, closing, submitting.
- **Accessibility**: labelled title and close action.
- **Motion**: opacity and translate only.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Button press, selected state |
| Standard | 220ms | ease-in-out | Modal and panel transitions |
| Emphasis | 420ms | cubic-bezier(0.16, 1, 0.3, 1) | Preview reveal |

### Rules

- Animate only transform, opacity, and filter.
- Every interactive control has hover, active, focus-visible, and disabled states.
- `prefers-reduced-motion` disables non-essential transitions.

## 7. Depth & Surface

### Strategy

Mixed but restrained: borders define structure, tonal shifts define hierarchy, and shadows are reserved for overlays.

| Level | Value | Usage |
|-------|-------|-------|
| Border/default | 1px solid var(--border-default) | Cards, panels, inputs |
| Border/subtle | 1px solid var(--border-subtle) | Dividers and rows |
| Shadow/overlay | 0 24px 70px rgba(23, 33, 29, 0.14) | Modals and popovers |
| Shadow/card | 0 10px 28px rgba(23, 33, 29, 0.06) | Hovered cards only |
