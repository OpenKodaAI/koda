# Web App Design System & UI Principles

This file is the canonical reference for the Koda web app's design language. Apply these principles to every change under `apps/web/`.

This app is inside the root Obsidian Vault named `Koda`. Before asking the user
to repeat context, read:

```bash
obsidian vault=Koda read path="00_Index/Koda Workspace.md"
obsidian vault=Koda read path="60_Memory/Agent Operating Memory.md"
obsidian vault=Koda read path="60_Memory/User Preferences.md"
obsidian vault=Koda read path="60_Memory/Project Memory.md"
obsidian vault=Koda search query="<topic>" limit=10
```

If `obsidian read` is unavailable in this agent session, use:

```bash
../../../bin/koda-vault-read "60_Memory/User Preferences.md"
```

Persist durable preferences, project facts, and handoffs in `60_Memory/`.

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
- Shadows barely-there: `--shadow-xs: 0 1px 0 rgba(0,0,0,0.25)`, `--shadow-floating: 0 8px 28px rgba(0,0,0,0.45)`. No stacked `inset + outer` shadows.

### Glass-blur (mandatory for every overlay)

Every floating surface that overlays another surface MUST get glass-blur. There are exactly four canonical classes — the only correct way to ship an overlay is to apply one of them. The `backdrop-filter` rule on each is `!important` and must stay that way; do not introduce new bg/blur stacks.

| Class | Use for | Tokens |
| --- | --- | --- |
| `app-overlay-backdrop` | Dimmed scrim behind any modal/drawer (the layer that sits on top of the canvas). Pair with one of the panel classes below. | `--overlay-backdrop-bg` + `--overlay-backdrop-filter` |
| `app-modal-panel` | Centered modal/dialog panels (Command Bar, ConfirmationDialog, ConnectionModalRouter, agent/execution detail modals). | `--overlay-modal-bg` + `--overlay-modal-filter` |
| `app-drawer-panel` | Side drawers (Drawer primitive, audit/dlq/execution detail drawers). | `--overlay-modal-bg` + `--overlay-modal-filter` |
| `app-floating-panel` | Popovers, dropdowns, tooltips, select content, command menus, color picker panel, model selector — any portal-rendered floating menu. The `Popover`, `Tooltip`, and `Select` primitives compose this class. | `--overlay-floating-bg` + `--overlay-floating-filter` |

Rules:
- Never write a new floating surface with hand-rolled `bg-[...]` + `backdrop-blur-*` Tailwind utilities. Use one of the four classes above.
- **Render overlays through `createPortal(node, document.body)`**. Inline-rendered modals get clipped or fail to cover the viewport whenever an ancestor establishes a containing block (`transform`, `filter`, `perspective`, `will-change: transform`) — `position: fixed` then resolves against that ancestor instead of the viewport. The agent-catalog workspace/squad edit modal hit this and failed to cover the page; it now portals to body.
- Never set `backdrop-filter: none` on any of those classes (or selectors targeting them) in any theme. The light-theme overrides at the bottom of `globals.css` are scoped to `::before` sheen pseudo-elements and a few non-overlay surfaces — do not extend them to the panels themselves.
- Do not stack a floating panel inside another floating panel — glass-on-glass blurs the wrong layer (the parent panel's bg). If a popover needs a sub-popover, render both as siblings via Portal.
- The `!important` on `backdrop-filter` exists because Tailwind v4's backdrop utilities and downstream theme resets historically shadowed the rule. Keep it.

The contract is enforced by `tests/test_glass_blur_contract.py` (Python) and the unit test in `apps/web/src/app/__tests__/glass-blur.test.ts`. Both must pass.

### Overlay enter/exit animation (mandatory)

Modal/drawer/popover open and close must never feel abrupt. Pair the glass-blur class with the matching animation class and drive both from `useAnimatedPresence` (`@/hooks/use-animated-presence`).

| Animation class | Surface |
| --- | --- |
| `app-overlay-anim` | The scrim (`app-overlay-backdrop`). |
| `app-modal-anim` | Centered modal panels (`app-modal-panel`). |
| `app-drawer-anim-right` | Right-side drawers. |
| `app-drawer-anim-left` | Left-side drawers. |
| `app-floating-anim` | Inline-portaled floating menus (e.g. `CommandBar` inline dropdown). Subtle fade + 4px lift + 0.98 scale, faster (160ms) than modals. |
| Radix data-state animations | `Drawer`, `Popover`, `Tooltip`, `Select`, `CommandBarModal` (already wired via `data-[state=open]:animate-in`). |
| Framer Motion | `agent-switcher`, `language-switcher`, `settings-warning-indicator`, `agent-catalog`'s `WorkspaceSelectorDropdown` / `CreatePopover`, `tour-coachmark` — these have bespoke choreography, leave them. |

Pattern:

```tsx
const presence = useAnimatedPresence(open, null, { duration: 200 });
useBodyScrollLock(presence.shouldRender);
useEscapeToClose(presence.shouldRender, onClose);
if (!presence.shouldRender) return null;

return createPortal(
  <>
    <div
      className="app-overlay-backdrop app-overlay-anim"
      data-visible={presence.isVisible}
      onClick={onClose}
    />
    <div className="app-modal-frame …">
      <div
        className="app-modal-panel app-modal-anim …"
        data-visible={presence.isVisible}
      >…</div>
    </div>
  </>,
  document.body,
);
```

Rules:
- The animations are **`@keyframes`-based**, not `transition`-based. The enter keyframe (`app-modal-enter`, `app-overlay-enter`, etc.) fires the moment the element is inserted in the DOM, regardless of whether React batched the presence state into a single paint. Do not refactor these back into `transition: opacity ...` rules — the previous transition-based approach silently no-op'ed on open and is what made modals look "abrupt".
- Never write `animation: ... var(--transition-base) ...`. The token is a `transition` shorthand, not an `animation` shorthand; the browser will reject the rule. Inline the duration + easing directly inside the `animation` declaration.
- The `duration` you pass to `useAnimatedPresence` MUST match (or slightly exceed) the longest exit keyframe duration in CSS, otherwise the element either unmounts mid-animation or sticks around after fade-out. Current values: 180ms (overlay/modal exit), 200ms (drawer exit).
- For non-presence surfaces (where the parent unmounts on close), the enter keyframe still fires automatically on mount — no local state flag needed. Exit will be abrupt; that's only acceptable for parent-managed dismissal.
- Tests asserting on portal-rendered overlays should use `findByRole` / `await waitFor`, not synchronous `getByRole` — the presence helper still defers mount by one effect tick.
- The hook intentionally mirrors a prop into state inside an effect (with an `eslint-disable react-hooks/set-state-in-effect` block). That's the textbook valid case for the rule — don't "fix" it by introducing derived state, since the delayed unmount needs persistent state.

## Motion

- Default easing: `cubic-bezier(0.22, 1, 0.36, 1)` (token `--ease-out-quart`).
- Durations: `--transition-fast: 120ms`, `--transition-base: 200ms`, `--transition-slow: 320ms`.
- Hover never uses `transform: scale` — only `background-color`, `border-color`, `color` transitions + overlay tint.
- Press feedback: `active:scale-[0.96]` only on accent CTAs.
- Framer-motion reserved for: page route enter, drawer open/close, tab content fade, status pulse. **Do not** use it for list items — prefer CSS `.stagger-N` + `animate-in`.
- Honor `prefers-reduced-motion: reduce` (global rule already in [`globals.css`](src/app/globals.css)).

## Components (canonical sizes)

Primitives live under `apps/web/src/components/ui/` and `apps/web/src/components/dashboard/`.

- **Button** heights: `lg` 36 / `md` 32 / `sm` 28. Radius `--radius-panel-sm`. Variants: `primary`, `accent`, `mono`, `destructive`, `secondary`, `outline`, `ghost`, `dim`, `foreground`.
- **Input / Select**: default `h-9` (36px), radius `--radius-input` (14px), bg `--panel-soft`, focus ring `--accent` with `box-shadow: 0 0 0 1px var(--accent-muted)`.
- **SoftTabs** ([`ui/soft-tabs.tsx`](src/components/ui/soft-tabs.tsx)): outer `h-9 p-0.5 rounded-pill`, inner buttons `h-8 px-3`.
- **Tooltip**: `max-w-220`, `text-[0.75rem]`, radius-chip 8. Glass surface — `--overlay-floating-bg` + `--overlay-floating-filter`.
- **Modal / Drawer** ([`ui/drawer.tsx`](src/components/ui/drawer.tsx)): Radix Dialog wrapper. Drawers use `modal={false}` by default to preserve context behind. Single panel, radius-shell 14. Glass surface — `--overlay-modal-bg` + `--overlay-modal-filter`; the backdrop scrim uses `--overlay-backdrop-*`.
- **Popover** ([`ui/popover.tsx`](src/components/ui/popover.tsx)): Radix Popover wrapper. Radius-panel 12, border-subtle, shadow-floating. Glass surface — `--overlay-floating-bg` + `--overlay-floating-filter`. Same treatment for `Select` content and any portal-rendered floating menu (`.app-floating-panel`).
- **Card** ([`ui/card.tsx`](src/components/ui/card.tsx)): flat, single variant. Radius-panel 12, border-subtle, no shadow. Header border uses `--divider-hair`.
- **ConnectionModalRouter** ([`editor/tabs/connection/connection-modal-router.tsx`](src/components/control-plane/editor/tabs/connection/connection-modal-router.tsx)): per-agent integration connect modal. Routes to sub-forms based on the catalog's `ConnectionProfile.strategy` (`oauth_only`, `oauth_preferred`, `api_key`, `connection_string`, `dual_token`, `local_path`, `local_app`, `none`). Never branch on integration name inside UI — declare the profile in the catalog instead.
- **DynamicConstraintsPanel** ([`editor/tabs/constraints/dynamic-constraints-panel.tsx`](src/components/control-plane/editor/tabs/constraints/dynamic-constraints-panel.tsx)): renders only the runtime constraints the integration declares (`allowed_domains`, `allowed_paths`, `allowed_db_envs`, `allow_private_network`, `read_only_mode`). If the integration doesn't declare a key, the control is not in the DOM.
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
- Stabilize payload identity with a `useContentStable(value)` hook (pattern in [`hooks/use-agent-stats.ts`](src/hooks/use-agent-stats.ts)) — uses `useMemo` with a JSON key to return the previous reference when content is structurally identical.
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

## Auth screens (`/setup`, `/login`, `/forgot-password`, `/settings/account`)

- These routes run behind a tighter Content-Security-Policy than the rest of the app. `script-src` is `'self' 'unsafe-inline'` because Next.js App Router injects inline RSC bootstrap scripts, but external origins, framing, and `<object>` embedding are disabled. Do not introduce `dangerouslySetInnerHTML` or third-party inline scripts that would widen the policy further.
- Every authentication error ("wrong password", "unknown user", "invalid recovery code", "rate-limited") is funneled through a single generic translation key. Never introduce a branch that renders a specific error message — the backend already makes them indistinguishable to neutralize timing and enumeration attacks.
- The new setup flow is strictly two screens (`step-create-account` → `step-recovery-codes`) in `src/components/setup/`. Do not re-introduce provider / GitHub / Telegram / allowed-user fields into the setup wizard; those belong to the optional post-setup checklist ([`src/components/dashboard/setup-checklist-card.tsx`](src/components/dashboard/setup-checklist-card.tsx)) and their existing drawers in `/control-plane`.
- See [`../../docs/security/authentication.md`](../../docs/security/authentication.md) for the canonical contract.

## Related guidance

- Root operational guide: [`../../CLAUDE.md`](../../CLAUDE.md).
- Architecture overview: [`../../docs/architecture/overview.md`](../../docs/architecture/overview.md).
- Design primitives live in `src/components/ui/` — the source of truth; never fork a primitive inline.
