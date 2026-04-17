# Web App Design System & UI Principles

This file mirrors [`CLAUDE.md`](CLAUDE.md) for `AGENTS.md`-aware tooling (Codex and similar). Read `CLAUDE.md` as the canonical reference — both files must stay aligned.

Apply these principles to every change under `apps/web/`.

## Identity

- **Dark-first**, canonical state. Light mode secondary.
- Inspired by claude.ai, claude.com/product/overview, claude.com/product/claude-code.
- Compact, minimalist, low-density. "Suspenso" content over nested cards.

## Color palette

Tokens in [`src/app/globals.css`](src/app/globals.css):
- Surfaces: `--canvas: #0C0C0C`, `--shell: #121212`, `--panel: #161616`, `--panel-soft: #141414`, `--panel-strong: #1F1F1F`.
- Accent: `--accent: #D97757` — single CTA per screen + focus rings. Never decorative.
- Borders: `--border-subtle: #1F1F1F`, `--border-strong: #2A2A2A`, `--divider-hair: rgba(255,255,255,0.04)`.
- Text: `--text-primary: #F5F5F5` → `--text-quaternary: #6A6A6A`.
- Tones (`--tone-{success,info,warning,danger,retry,neutral}-{bg,dot,text,…}`): use `bg` soft by default, `bg-strong` only on `appearance="solid"`.

## Typography

- Body stack: `-apple-system, BlinkMacSystemFont, var(--font-inter), "Segoe UI", Roboto, system-ui, sans-serif`.
- `font-feature-settings: "cv11","ss01","ss03"`, `letter-spacing: -0.014em`.
- Mono: JetBrains Mono for eyebrows, timestamps, tabular numbers. Tracking `0.12em` uppercase.
- Scale: 12/13/14/15/17/22/32/44.
- Display weight 500, tracking `-0.04em`. Never bold headlines.

## Spacing & radius

- Multiples of 4 (`--space-1`…`--space-24`).
- Radius: chip 8 / panel-sm 10 / panel 12 / shell 14 / input 14 / pill 999.
- Shadows barely-there. No stacked `inset + outer`, no glass sheen.

## Motion

- Easing: `cubic-bezier(0.22, 1, 0.36, 1)`. Durations 120/200/320ms.
- Hover: only `background/border/color` transitions. Never `transform: scale`.
- Framer Motion reserved for route enter, drawer, tab fade, status pulse. Lists use CSS `.stagger-N`.
- Honor `prefers-reduced-motion: reduce`.

## Component sizes

Primitives under [`src/components/ui/`](src/components/ui/):
- Button: lg 36 / md 32 / sm 28. Radius `--radius-panel-sm`. Variants include `accent` for warm CTA.
- Input/Select: h-9 (36px), radius 14, focus ring `--accent`.
- SoftTabs: outer h-9 p-0.5 pill, inner buttons h-8.
- Tooltip: max-w-220, text-xs, radius 8, opaque `--panel-strong`.
- Drawer (Radix Dialog): `modal={false}` default. Single panel radius-shell 14.
- Popover (Radix Popover): radius-panel 12, shadow-floating.
- Card: flat, single variant, no shadow. `--divider-hair` internal borders.
- Badge / StatusBadge: soft `bg` default.
- StatusDot, InlineAlert, DetailGrid/DetailBlock/DetailDatum: extracted primitives, reuse across routes.
- PageSectionHeader accepts `compact`. PageMetricStripItem accepts `tone`.

## Icons

- Lucide React only.
- Utility classes `.icon-xs` (12) to `.icon-xl` (24). `.icon-md` (16) default in buttons/inputs.
- Prefer `strokeWidth={1.75}`.

## Silent polling (mandatory)

For every `useControlPlaneQuery` that polls:
- `notifyOnChangeProps: ["data", "error"]`.
- `placeholderData: keepPreviousData`.
- `refetchOnWindowFocus/Mount/Reconnect: false`.
- Stabilize data identity via `useContentStable` (JSON-based memo) — see [`src/hooks/use-bot-stats.ts`](src/hooks/use-bot-stats.ts).
- Wrap heavy list/grid consumers in `React.memo` with content comparators.
- Never `content-visibility: auto` on polled sections (causes paint flashes).

## UX rules

- No decorative noise (news pills, tips, promo banners, welcome callouts).
- Timestamps compact: `4m`, `2h`, `3d`.
- Status dots with `pulse` for running states; no spinners for polling.
- Empty states: single icon + sentence, no card.
- Greeting resolved client-side by hour.

## Layout

- Sidebar 15rem / 3.5rem collapsed.
- Topbar 56px flat, border-bottom `--divider-hair`.
- Main content max-w 1320 (cockpit) / 760 (hero).
- Rows separated by hair dividers, not card wrappers.

## Forbidden

- Glassmorphism stacking, nested containers, decorative illustrations.
- Purple gradients, emoji-heavy UI, non-configured fonts.
- Flash spinners on polls.
- Framer Motion before trying CSS.
- Hardcoded `rgba(255,255,255,0.X)` — use tokens.

## Before redesigning a route

1. Explore current tree.
2. Extract shared patterns as primitives first.
3. Preserve hooks/data flow; render-tree changes only.
4. Preserve test assertions (IDs, role selectors, labels).
5. `pnpm lint:web && pnpm test:web && pnpm build:web`.

## Related

- Root guide: [`../../AGENTS.md`](../../AGENTS.md).
- Detailed reference: [`CLAUDE.md`](CLAUDE.md).
- Primitives: [`src/components/ui/`](src/components/ui/).
