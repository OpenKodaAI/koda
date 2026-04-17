# Web App Design System & UI Principles

This file is the canonical reference for the Koda web app's design language. Apply these principles to every change under `apps/web/`. The matching [`AGENTS.md`](AGENTS.md) mirrors this guidance for Codex-style tooling.

## Identity

- **Dark-first, canonical state.** Light mode still works but is secondary. Never treat dark as an alternative.
- **Inspiration**: claude.ai, claude.com/product/overview, claude.com/product/claude-code. Refined minimalism, hair dividers, flat panels, accent warm.
- **Compact, minimalist, low-density-by-default.** Prefer "suspenso" (floating) content over nested card-in-card containers.

## Color palette (dark canonical)

Tokens live in [`apps/web/src/app/globals.css`](src/app/globals.css):

- `--canvas: #0C0C0C`, `--shell: #121212`, `--panel: #161616`, `--panel-soft: #141414`, `--panel-strong: #1F1F1F`.
- `--accent: #D97757` (Claude warm). Reserved for **single CTA per screen** (New session, Run, Submit) and focus rings. Never decorative, never for arbitrary highlights.
- `--border-subtle: #1F1F1F`, `--border-strong: #2A2A2A`, `--divider-hair: rgba(255,255,255,0.04)`.
- Text: `--text-primary: #F5F5F5`, `--text-secondary: #B8B8B8`, `--text-tertiary: #9A9A9A`, `--text-quaternary: #6A6A6A`.
- Tones: `--tone-{success,info,warning,danger,retry,neutral}-{bg,bg-strong,border,text,dot,muted}` — use `bg` for soft, `bg-strong` for solid appearance only.

**Hair dividers over borders.** `border-t border-[color:var(--divider-hair)]` between list rows instead of card wrappers.

## Typography

- Stack (body): `-apple-system, BlinkMacSystemFont, var(--font-inter), "Segoe UI", Roboto, system-ui, sans-serif` — macOS users get SF Pro natively; Inter as fallback.
- `font-feature-settings: "cv11", "ss01", "ss03"`, `letter-spacing: -0.014em`.
- Mono: JetBrains Mono for eyebrows, timestamps, tabular numbers. Eyebrow tracking `0.12em` uppercase.
- Scale: 12 / 13 / 14 (base) / 15 / 17 / 22 / 32 (display-sm) / 44 (display hero).
- Display weight: 500. Never bold headlines; tracking `-0.04em` for display.
- Hero greeting pattern: `var(--font-size-display)` (44px), `var(--tracking-display)`, weight 500.

## Spacing & radius

- Spacing scale multiples of 4 (tokens `--space-1`…`--space-24`).
- Radius tokens: `--radius-chip: 8` · `--radius-panel-sm: 10` · `--radius-panel: 12` · `--radius-shell: 14` · `--radius-input: 14` · `--radius-pill: 999`.
- Shadows barely-there: `--shadow-xs: 0 1px 0 rgba(0,0,0,0.25)`, `--shadow-floating: 0 8px 28px rgba(0,0,0,0.45)`. No stacked `inset + outer` shadows, no glassmorphism sheen (removed intentionally).

## Motion

- Default easing: `cubic-bezier(0.22, 1, 0.36, 1)` (token `--ease-out-quart`).
- Durations: `--transition-fast: 120ms`, `--transition-base: 200ms`, `--transition-slow: 320ms`.
- Hover never uses `transform: scale` — only `background-color`, `border-color`, `color` transitions + overlay tint.
- Press feedback: `active:scale-[0.96]` only on accent CTAs.
- Framer-motion reserved for: page route enter, drawer open/close, tab content fade, status pulse. **Do not** use it for list items — prefer CSS `.stagger-N` + `animate-in`.
- Honor `prefers-reduced-motion: reduce` (global rule already in [`globals.css`](src/app/globals.css)).

## Components (canonical sizes)

Primitives live under [`apps/web/src/components/ui/`](src/components/ui/) and [`apps/web/src/components/dashboard/`](src/components/dashboard/).

- **Button** heights: `lg` 36 / `md` 32 / `sm` 28. Radius `--radius-panel-sm`. Variants: `primary`, `accent`, `mono`, `destructive`, `secondary`, `outline`, `ghost`, `dim`, `foreground`.
- **Input / Select**: default `h-9` (36px), radius `--radius-input` (14px), bg `--panel-soft`, focus ring `--accent` with `box-shadow: 0 0 0 1px var(--accent-muted)`.
- **SoftTabs** ([`ui/soft-tabs.tsx`](src/components/ui/soft-tabs.tsx)): outer `h-9 p-0.5 rounded-pill`, inner buttons `h-8 px-3`.
- **Tooltip**: `max-w-220`, `text-[0.75rem]`, radius-chip 8, opaque `--panel-strong` bg. No glass blur.
- **Modal / Drawer** ([`ui/drawer.tsx`](src/components/ui/drawer.tsx)): Radix Dialog wrapper. Drawers use `modal={false}` by default to preserve context behind. Single panel, radius-shell 14, no `::before` sheens.
- **Popover** ([`ui/popover.tsx`](src/components/ui/popover.tsx)): Radix Popover wrapper. Radius-panel 12, border-subtle, shadow-floating.
- **Card** ([`ui/card.tsx`](src/components/ui/card.tsx)): flat, single variant. Radius-panel 12, border-subtle, no shadow. Header border uses `--divider-hair`.
- **Badge / StatusBadge**: default "soft tone" (`--tone-*-bg`, not `-bg-strong`). `bg-strong` only when `appearance="solid"` is explicit.
- **StatusDot** ([`ui/status-dot.tsx`](src/components/ui/status-dot.tsx)): dot colorized by tone with optional `pulse`. Use `StatusDot tone="info" pulse` for live/running indicators.
- **InlineAlert** ([`ui/inline-alert.tsx`](src/components/ui/inline-alert.tsx)): tonalized message block; tone-appropriate icon default.
- **DetailGrid / DetailBlock / DetailDatum** ([`ui/detail-group.tsx`](src/components/ui/detail-group.tsx)): metadata structures inside Drawers/Modals.
- **PageSectionHeader** compact variant (`compact={true}`) for dense cockpit headers.
- **PageMetricStrip / PageMetricStripItem**: `tone` prop (`accent`/`warning`/`danger`/`success`) applies color to value; hair divider between items, no card wrapper.
- **ActivityHeatmap** ([`dashboard/activity-heatmap.tsx`](src/components/dashboard/activity-heatmap.tsx)): GitHub-style grid, cells max 28px, 5px gap, accent-gradient intensity.
- **ExecutionHistory** ([`dashboard/execution-history.tsx`](src/components/dashboard/execution-history.tsx)): suspended list pattern — grid `[200px_minmax(0,1fr)_auto]` with glyph/name · query · status+time stacked.
- **EventRow** ([`runtime/shared/event-row.tsx`](src/components/runtime/shared/event-row.tsx)): unified log/event row pattern.

## Icons

- Lucide React is the only icon library.
- Utility classes: `.icon-xs` (12) · `.icon-sm` (14) · `.icon-md` (16, default in inputs/buttons) · `.icon-lg` (20, nav) · `.icon-xl` (24, hero).
- Prefer `strokeWidth={1.75}` to match Claude aesthetic.

## Silent data refresh (mandatory for polling routes)

Subscribers to polled queries must never cause visible re-renders or flicker. In every `useControlPlaneQuery` that polls:

- `notifyOnChangeProps: ["data", "error"]` — skip re-renders on `isFetching` flips.
- `placeholderData: keepPreviousData` — preserve last data during refetch.
- `refetchOnWindowFocus: false`, `refetchOnMount: false`, `refetchOnReconnect: false`.
- Stabilize payload identity with a `useContentStable(value)` hook (pattern in [`hooks/use-bot-stats.ts`](src/hooks/use-bot-stats.ts)) — uses `useMemo` with a JSON key to return the previous reference when content is structurally identical.
- Heavy consumer components (lists, grids, heatmaps) must be wrapped in `React.memo` with a content-based comparator.
- Do NOT use `content-visibility: auto` on sections that may re-render — causes paint flashes.

## UX rules

- **No decorative UI noise.** Do not add "Latest news" pills, welcome banners, tip cards, promo callouts, version badges, or other passive elements the user is unlikely to interact with. Every element must be actionable or informative with high signal.
- **Timestamps** in compact format: `4m`, `2h`, `3d`, `2mo ago`. Never `4 min. ago`.
- **Status indicators** (running/retrying): dot with `pulse` + optional typing-dots shimmer for running state. No spinners.
- **Polling** invisible to user; only data updates on success.
- **Empty states** tonalized in `--text-tertiary`, small icon, single sentence. Never a card.
- **Greeting** resolves time-of-day client-side (`new Date().getHours()` with `morning/afternoon/evening/night`).
- **Breadcrumbs / titles** use `PageSectionHeader compact` for dense views, full for landing-style.

## Layout principles

- **Sidebar** expanded 15rem / collapsed 3.5rem. No left accent bar on active item — just pill `bg-[var(--panel-strong)]`.
- **Topbar** height 56px (`--shell-topbar-height`), flat `bg-[var(--shell)]`, border-bottom `--divider-hair`. Max 1 action rail.
- **Main content** max-width 1320px (cockpit routes), 760px (hero-centered routes like Home greeting + composer).
- **Row density**: hair dividers between rows; no card-per-row wrapping.
- **Full-bleed routes** (`/sessions`, `/runtime/[botId]/tasks/[taskId]`): topbar may be hidden; drawer instead of modal.

## What NOT to do

- No glassmorphism stacking (`backdrop-filter` + sheen gradients). Removed intentionally.
- No nested containers (`Card` inside `Card`; `app-toolbar-card` wrapping filters).
- No decorative illustrations in operational pages.
- No purple gradients, no emoji-heavy UI, no Inter-imitator fonts beyond what's configured.
- No "loading..." text spinners or skeleton banners that flash on polling. Refetches are silent.
- Do not introduce Framer Motion for a feature before trying CSS first.
- Do not hardcode `rgba(255,255,255,0.X)` — use tokens (`--hover-tint`, `--divider-hair`, etc.).

## Before redesigning a route

1. Read the current component tree (Explore agent or direct Grep).
2. Identify shared patterns that should become primitives under `components/ui/` or route-shared folder.
3. Extract primitives first, then wire them into the route — reuse across other routes.
4. Preserve all hooks/data flow; redesign is render-tree-only.
5. Check `CLAUDE.md` of the specific subtree for route-level invariants.
6. Update or preserve test-visible assertions (test IDs, role selectors, button labels).

## Required validation (web)

Every change under `apps/web/` must pass:

- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`

## Related guidance

- Root operational guide: [`../../CLAUDE.md`](../../CLAUDE.md).
- Architecture overview: [`../../docs/ai/architecture-overview.md`](../../docs/ai/architecture-overview.md).
- Design primitives live in [`src/components/ui/`](src/components/ui/) — the source of truth; never fork a primitive inline.
