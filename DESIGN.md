# ElfieNest Console Design System

## Product Feel
ElfieNest console is a local household operations dashboard for managing embodied AI companions, their shared nest, and the model "food" system that keeps them alive. It should feel quiet, grounded, and operational rather than decorative or marketing-led.

## Tokens
- Surfaces: `--surface-base`, `--surface-primary`, `--surface-secondary`, `--surface-elevated`, `--surface-inset`
- Text: `--text-primary`, `--text-secondary`, `--text-tertiary`
- Accent: `--accent-primary`, `--accent-hover`, `--accent-soft`, with amber and indigo for secondary status meaning
- Status: `--status-success`, `--status-warning`, `--status-error`, `--status-info`
- Spacing: `--space-1` through `--space-12`, based on 4px steps
- Radius: `--radius-1` through `--radius-3`, keeping dashboard cards at 8px or below
- Type: Avenir Next / SF Pro Display stack with tabular mono for metrics, logs, and technical identifiers

## Layout
The app uses a left sidebar with grouped navigation, a sticky topbar, and dense but readable dashboard panels. Repeated entities use cards or tables; whole sections stay unframed except for functional panels.

## Components
- Navigation groups with short labels and icon buttons
- Metric cards for system summaries
- Entity cards for Elfies and provider status
- Table panels for users and model catalog
- Settings tabs inside detail views, not as extra sidebar entries
- Drawers for adoption/profile flows

## Rules
- Keep CJK labels short and stable in the sidebar.
- Do not combine Elfie management and nest management; they represent private companions and shared space.
- Admin views may expose operational and model configuration; user views only expose owned Elfies and read-only nest visibility.
- Use the existing CSS variables before introducing new raw values.
