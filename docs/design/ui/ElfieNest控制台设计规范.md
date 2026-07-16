# ElfieNest 控制台设计规范

## Product Feel

ElfieNest console is a quiet local household operations dashboard for embodied AI companions, their shared nest, and the model "food" system that keeps them alive. It should feel grounded, dense, and operational rather than decorative or marketing-led.

The visual signature is a soft technical habitat: neutral work surfaces, subtle grid texture, restrained green accents, and configuration panels that are easy to scan.

## Product Rules

- Keep CJK labels short and stable in the sidebar.
- Do not combine Elfie management and nest management; private companions and shared nest space are separate product concepts.
- Owner 视图可以暴露服务运维、用户、精灵巢、模型和 Provider 配置；旧的 admin 角色不再作为产品导航或配置权限入口。
- User views only expose owned Elfies and read-only nest visibility, with limited permitted actions such as viewing layout and camera status.
- Model provider setup, model catalog, and food strategy belong together, but provider credentials and model routing should remain distinct inside the page.
- Use the existing CSS variables before introducing new raw values.

## Color

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| Surface/base | `--surface-base` | `#F6F8F7` | `#101513` | App background |
| Surface/primary | `--surface-primary` | `#FFFFFF` | `#171D1A` | Primary panels |
| Surface/secondary | `--surface-secondary` | `#EEF3F0` | `#202822` | Sidebar and quiet bands |
| Surface/elevated | `--surface-elevated` | `#FFFFFF` | `#232B26` | Popovers and modals |
| Surface/inset | `--surface-inset` | `#E8EFEB` | `#151B18` | Inputs and data wells |
| Text/primary | `--text-primary` | `#17211D` | `#F4F8F5` | Main text |
| Text/secondary | `--text-secondary` | `#617069` | `#BAC7C0` | Secondary text |
| Text/tertiary | `--text-tertiary` | `#87938D` | `#83918A` | Muted metadata |
| Border/default | `--border-default` | `#DCE5DF` | `#314038` | Cards and inputs |
| Border/subtle | `--border-subtle` | `#EDF2EF` | `#25312C` | Dividers and grid lines |
| Accent/primary | `--accent-primary` | `#177A63` | `#4AC29A` | Primary actions |
| Accent/hover | `--accent-hover` | `#0F5F4E` | `#7CDAB8` | Primary hover |
| Accent/soft | `--accent-soft` | `#DDF3EA` | `#173A31` | Selected states |
| Accent/amber | `--accent-amber` | `#8C6D1F` | `#E2BD4F` | Warnings and setup guidance |
| Accent/indigo | `--accent-indigo` | `#445C8A` | `#8EA8DE` | Model and route markers |
| Status/success | `--status-success` | `#2E7D57` | `#70D69B` | Healthy states |
| Status/warning | `--status-warning` | `#A1661B` | `#E5B86D` | Cautions |
| Status/error | `--status-error` | `#B94A48` | `#F19A98` | Errors and destructive actions |
| Status/info | `--status-info` | `#3B6F80` | `#86C5D4` | Informational states |

Large surfaces stay neutral. Accent colors are reserved for hierarchy, state, and commands. Provider and model status use semantic status tokens, never arbitrary colors.

## Typography

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

Primary font stack: `"Avenir Next", "SF Pro Display", "Helvetica Neue", Arial, sans-serif`.

Mono font stack: `"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`.

Body text in controls never drops below 13px. Page headings are compact because this is an operational console. Letter spacing is always 0.

## Spacing And Layout

All spacing derives from a 4px base.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Tight joins |
| `--space-2` | 8px | Icon gaps |
| `--space-3` | 12px | Input padding |
| `--space-4` | 16px | Panel padding |
| `--space-5` | 20px | Group spacing |
| `--space-6` | 24px | Card padding |
| `--space-8` | 32px | Major panel gaps |
| `--space-10` | 40px | Page section rhythm |
| `--space-12` | 48px | Wide workspace margins |

The app shell uses a fixed desktop sidebar plus a fluid workspace. The main workspace should use the available width; repeated cards collapse from three columns to one column.

Breakpoints:

- Mobile: below 760px
- Tablet: 760px to 1100px
- Desktop: above 1100px

Cards are limited to repeated items, framed tools, modals, and dashboards. Whole page sections stay unframed unless they are functional panels.

## Navigation Model

Owner 导航按任务域分组：

- 家庭管理：精灵管理、精灵巢管理、用户管理。
- 模型粮食：Provider 管理、模型目录、粮食策略。
- 运行运维：总览、服务、日志、运行时健康。
- 系统设置：只放核心全局设置，细分项放在页面内部标签中，不在侧边栏无限展开。

Regular users keep only Elfie management and nest visibility. Their Elfie page shows owned companions; their nest page is read-only except for permitted observation actions.

## Components

### App Shell

- Structure: sidebar, topbar, main workspace, optional modal overlays.
- 变体：Owner 控制台和普通用户工作区。
- States: active navigation, mobile collapsed nav, authenticated profile.
- Accessibility: nav and main landmarks, visible focus.
- Motion: panel changes use opacity and transform only.

### Metric Card

- Structure: label, numeric value, supporting text.
- Variants: healthy, warning, informational.
- States: loading skeleton, empty fallback.
- Accessibility: data is text, not decorative-only color.

### Data Card

- Structure: heading, status badge, metadata, action row.
- Variants: provider, model, Elfie, command, setup step.
- States: hover, active, saving, error, empty.
- Motion: hover transform only.

### Table Panel

- Use for users, model catalogs, logs, and technical inventories.
- Keep row actions compact and icon-first when a familiar icon exists.
- Avoid nested cards inside table panels.

### Config Form

- Structure: labeled field groups, inline help, action footer.
- Variants: LLM provider, model route, adoption, engine, security, profile.
- States: loading, dirty, saving, saved, error.
- Accessibility: every input has a label.

### Modal

- Structure: backdrop, header, body, footer actions.
- Variants: provider edit, user edit, profile, password.
- Accessibility: labelled title and close action.
- Motion: opacity and translate only.

## Motion And Surface

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | ease-out | Button press, selected state |
| Standard | 220ms | ease-in-out | Modal and panel transitions |
| Emphasis | 420ms | cubic-bezier(0.16, 1, 0.3, 1) | Preview reveal |

Animate only transform, opacity, and filter. Every interactive control has hover, active, focus-visible, and disabled states. `prefers-reduced-motion` disables non-essential transitions.

Depth is mostly borders and tonal shifts. Shadows are reserved for overlays and hovered cards.
