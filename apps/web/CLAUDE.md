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
Record task handoffs in the daily note or a session note. Do not store secrets
or raw environment values.

Before non-trivial work under `apps/web/`, also:

1. Read the root operational guide, [`../../CLAUDE.md`](../../CLAUDE.md), from the main repository root.
2. Search Obsidian for task-specific context before asking the user to repeat it.
3. Inspect the relevant component, route, hook, API, and tests before editing.

## Identity

- **Both themes are first-class; the default follows the system.** `DEFAULT_THEME_PREFERENCE` is `"system"` ([`components/providers/theme.ts`](src/components/providers/theme.ts)): the app renders dark or light from `prefers-color-scheme` until the user pins one (`html[data-theme]`). The palette below lists the dark values; every light token has its own value in `:root`. Check every change in both themes.
- **Inspiration**: claude.ai, claude.com/product/overview, claude.com/product/claude-code. Refined minimalism, hair dividers, flat panels, monochrome accent.
- **Compact, minimalist, low-density-by-default.** Prefer "suspenso" (floating) content over nested card-in-card containers.

## Color palette (dark canonical)

Tokens live in [`apps/web/src/app/globals.css`](src/app/globals.css):

- `--canvas: #0C0C0C`, `--shell: #121212`, `--panel: #161616`, `--panel-soft: #141414`, `--panel-strong: #1F1F1F`.
- `--accent: #FFFFFF` dark / `#000000` light (monochrome), with `--accent-text` (`#000000` / `#FFFEFB`) on it and `--accent-hover`. Reserved for the **single CTA per screen** (New session, Run, Submit). Never decorative, never for arbitrary highlights, and never the focus indicator: focus uses `--focus-ring` (see Focus).
- `--border-subtle: #1F1F1F`, `--border-strong: #2A2A2A`, `--divider-hair: rgba(255,255,255,0.04)`.
- Text: `--text-primary: #F5F5F5`, `--text-secondary: #B8B8B8`, `--text-tertiary: #9A9A9A` (light `#615b54`), `--text-quaternary: #8A8A8A` (light `#655e57`). `--text-quaternary` is text, so it keeps 4.5:1 on every surface token text sits on and on the modal and floating glass (D-267). Two backgrounds take it lower, so text on them uses `--text-tertiary` or stronger: the pressed fills (`--surface-hover-strong`, `--surface-tint-strong`), and a `--hover-tint` highlight on the modal glass (4.37:1 in light), such as the command palette's active option or a hovered row in a dialog. `src/components/ui/focus-ring-contract.test.tsx` checks it, the palette's active option included.
- In light, holding 4.5:1 on the modal glass leaves `--text-quaternary` (5.96:1 on the canvas) almost as dark as `--text-tertiary` (6.26:1), so light shows three visible text steps, not four. That is the chosen trade-off: a quaternary text that fails AA is worse than a lost step.
- Tones: `--tone-{success,info,warning,danger,retry,neutral}-{bg,bg-strong,border,text,dot,muted}` — use `bg` for soft, `bg-strong` for solid appearance only. There is no `-tint` step; a soft tone fill is `-bg`.
- **Only defined tokens.** Every `var(--name)` in a component, helper or `globals.css`, and every Tailwind v4 shorthand that compiles to one (`bg-(--name)`, `border-(color:--name)`), must name a custom property the app defines (`globals.css`, an inline style, a Tailwind `[--name:value]` property or next/font's `variable`); only Radix's `--radix-*` and Tailwind's `--tw-*` come from libraries. An undefined `var()` invalidates its whole declaration (a background turns transparent) and nothing reports it, and a `var(--hook, fallback)` that nothing sets is dead: write the value. `src/lib/token-reference-contract.test.ts` enforces this. The surface names are `--canvas`, `--shell`, `--panel`, `--panel-soft`, `--panel-strong` and the `--surface-*` family; there is no `--surface-canvas`, `--surface-base` or `--panel-muted`.

**Hair dividers over borders.** `border-t border-[color:var(--divider-hair)]` between list rows instead of card wrappers.

## Typography

- Stack (body): `var(--font-inter), "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif` — Inter (loaded by next/font in [`app/layout.tsx`](src/app/layout.tsx)) on every platform; the system fonts are fallbacks only. Body size `0.875rem` (`0.8125rem` under 768px), line-height 1.3.
- `font-feature-settings: "cv11", "ss01", "ss03"`, `letter-spacing: -0.014em`.
- Mono: JetBrains Mono for eyebrows, timestamps, tabular numbers. Eyebrow tracking `0.12em` uppercase.
- Scale: 12 / 13 / 14 (base) / 15 / 17 / 22 / 32 (display-sm) / 44 (display hero), as `--font-size-{xs,sm,base,md,lg,xl,display-sm,display}`. New and touched text stays on the scale; older arbitrary sizes (`text-[10px]`, `text-[0.6875rem]`, …) are legacy and move to it when their component is touched. A font-size token in a Tailwind class needs the `length:` hint (`text-[length:var(--font-size-sm)]`): `text-[var(--font-size-sm)]` compiles to `color:`, not `font-size:`. Tailwind's `text-xs` (12px) and `text-sm` (14px) are on the scale. The global `.eyebrow` class sets 10.5px outside any layer, so it overrides every size utility on its element: a touched eyebrow drops the class for `font-mono text-xs font-medium uppercase tracking-[var(--tracking-mono)]` (the command palette's group headings).
- Display weight: 500. Never bold headlines; tracking `-0.04em` for display.
- Hero greeting pattern: `var(--font-size-display)` (44px), `var(--tracking-display)`, weight 500.

## Spacing & radius

- Spacing scale multiples of 4 (tokens `--space-1`…`--space-24`).
- Radius tokens: `--radius-chip: 8` · `--radius-panel-sm: 10` · `--radius-panel: 12` · `--radius-shell: 14` · `--radius-input: 14` · `--radius-pill: 999`.
- New and touched components use the radius tokens (`rounded-[var(--radius-panel)]`, …) rather than Tailwind's `rounded-lg` / `rounded-xl` or raw values such as `rounded-[22px]`; a text field takes `--radius-input`. The raw radii elsewhere are legacy.
- **No shadows paint.** The flat-design reset near the bottom of `globals.css` (`box-shadow: none !important` on every element and pseudo-element, except a focused form field) nulls them all, and the light `--shadow-*` tokens are `none`. Depth comes from borders, the surface steps and the glass overlays. Do not add `shadow-*` utilities or `box-shadow` rules: they never paint.

### Focus (mandatory)

- Keyboard focus is always visible, in both themes. `--focus-ring` (`#8A8A8A` dark, `#6F685F` light) keeps at least 3:1 contrast against every surface token (`--canvas` … `--surface-elevated-soft`) and against the accent CTA fill. A surface outside those tokens sets `--focus-ring` locally to a colour that keeps 3:1 there: the toast uses its own text colour on the tone fills, and the tour coachmark uses `--text-secondary` on its glass card. `src/components/ui/focus-ring-contract.test.tsx` enforces all of this.
- One focus indicator per control (decision M8-E1-T1, D-114):
  - **Controls that are not form fields** (buttons, links, the Select trigger, menu options, tabs, native checkboxes and radios): the global 2px `--focus-ring` outline. It is unlayered CSS, so Tailwind `outline-none` / `outline-hidden` (in `@layer utilities`) cannot remove it, and the flat-design reset nulls box-shadow on these elements, so `ring-*` / `shadow-*` focus utilities on them never paint. Do not add them; the contract test scans every component and fails on a `focus:`/`focus-visible:` `ring-*`, `shadow-*`, `outline-none` or `outline-hidden` utility outside a form field. To restyle a control's ring, set `outline` / `outline-offset` in a component rule, in `--focus-ring`.
  - **Form fields** (`input` other than checkboxes and radios, `textarea`, `select`, `[contenteditable="true"]`): the global `!important` rule removes their outline, so each draws its own ring with box-shadow. `.field-shell` draws it for the fields it styles; on a `<button>` (the ModelSelector trigger) it leaves the global outline in place. Text fields recolor their border to `--focus-ring` (or `--accent` on the auth screens) and add a 1px ring of the same colour; every range input, `.ui-slider` or not, adds a 2px `--focus-ring` ring (`input[type="range"]:focus-visible`). The flat-design reset near the bottom of `globals.css` is `html body *:where(:not(:is(input, textarea, select, [contenteditable="true"]):focus-visible))`: it spares only these fields while they hold focus, so their ring paints. Keep their focused state free of decorative shadows, because the reset no longer hides them there.
  - **Wrappers that frame a bare field** (search boxes, composers, `TagInputField`): the reset nulls the wrapper's box-shadow, so draw the ring with an outline: `focus-within:border-[color:var(--focus-ring)] focus-within:outline focus-within:outline-[color:var(--focus-ring)]` (add `focus-within:-outline-offset-1` on a borderless wrapper). Never `focus-within:shadow-*` or `focus-within:ring-*`.
  - **Dimmed controls**: opacity dims the outline or ring painted inside the element too. A control dimmed with an `opacity-*` utility (the toast buttons, the inheriting EffortPicker slider and number field) adds `focus-visible:opacity-100`; a dimmed group around focusable controls (the inheriting EffortPicker tabs) adds `has-[:focus-visible]:opacity-100`. The contract test checks the toast, the inheriting EffortPicker and the dimmed session surfaces (the pending user message, a submitted ui-form, the system_event row and the room composer while it submits); it does not find dimmed controls elsewhere.
- Do not widen the box-shadow reset or raise its specificity, and do not add another `box-shadow: none !important` that matches a focused form field. Never use a translucent token such as `--accent-muted` as the only focus indicator.

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

The contract is enforced by the unit test in [`src/lib/glass-blur-contract.test.ts`](src/lib/glass-blur-contract.test.ts).

### Overlay enter/exit animation (mandatory)

Modal/drawer/popover open and close must never feel abrupt. Pair the glass-blur class with the matching animation class and drive both from `useAnimatedPresence` (`@/hooks/use-animated-presence`).

| Animation class | Surface |
| --- | --- |
| `app-overlay-anim` | The scrim (`app-overlay-backdrop`). |
| `app-modal-anim` | Centered modal panels (`app-modal-panel`). |
| `app-drawer-anim-right` | Right-side drawers. |
| `app-drawer-anim-left` | Left-side drawers. |
| `app-floating-anim` | Inline-portaled floating menus (e.g. `CommandBar` inline dropdown). Subtle fade + 4px lift + 0.98 scale, faster (160ms) than modals. |
| Radix data-state animations | `Drawer`, `Popover`, `Tooltip`, `Select`, `CommandBarModal` (already wired via `data-[state=open]:animate-in`). `LanguageSwitcher` is a Radix Select too; Radix Select unmounts its list on close, so the switcher fades out an inert, `aria-hidden` copy of the list for 160ms. Do not keep the Root open for an exit fade: Radix would keep the keyboard, the focus trap and the page lock through it. |
| Framer Motion | `agent-switcher`, `settings-warning-indicator`, `agent-catalog`'s `WorkspaceSelectorDropdown` / `CreatePopover`, `tour-coachmark` — these have bespoke choreography, leave them. |

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

- **Button** ([`ui/button.tsx`](src/components/ui/button.tsx)) heights: `lg` 44 (`h-11`) / `md` 40 (`h-10`) / `sm` 36 (`h-9`); `icon` is 40 square. Radius `--radius-panel-sm`. Variants: `primary`, `accent`, `mono`, `destructive`, `secondary`, `outline`, `dashed`, `ghost`, `dim`, `foreground`, `inverse`.
- **Input / Textarea / Select**: default `h-9` (36px), radius `--radius-input` (14px), bg `--panel-soft`. On focus, Input and Textarea turn their border `--focus-ring` and add a 1px `--focus-ring` ring (`focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]`); the Select trigger is a button, so its ring is the global outline.
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

Every change under `apps/web/` must pass, run from the repository root:

- `pnpm lint:web`
- `pnpm test:web`
- `pnpm build:web`

Run narrower tests during implementation when possible.

## Auth screens (`/setup`, `/login`, `/forgot-password`, `/settings/account`)

- These routes run behind a tighter Content-Security-Policy than the rest of the app. `script-src` is `'self' 'unsafe-inline'` because Next.js App Router injects inline RSC bootstrap scripts, but external origins, framing, and `<object>` embedding are disabled. Do not introduce `dangerouslySetInnerHTML` or third-party inline scripts that would widen the policy further.
- Every authentication error ("wrong password", "unknown user", "locked account", "invalid recovery code") is funneled through a single generic translation key. Never introduce a branch that renders a specific error message for them — the backend answers them all with the same response, so a distinct message would tell a caller which accounts exist. The backend also makes every rejected sign-in take the same time, with a dummy Argon2 check and a fixed 300 ms floor, and every rejected password recovery, with the same recovery-code lookup and the same floor (D-136).
- The only allowed exceptions are two answers that depend on the client, never on an account. Do not add another; `src/lib/auth-error-contract.test.ts` checks that the screens and every module they import, directly or not, read none of the fields an `ApiError` takes from the response except for these two answers and the "service unavailable" check: the error code (`reason`), the HTTP status (`status`), what `src/lib/errors.ts` derives from the status (`code`, `retryable`) and the `Retry-After` wait (`retryAfterSeconds`). An error-copy helper is scanned like the screen that imports it; only the modules that test lists by name (the error plumbing, and components whose own prop is called `status`) are reviewed instead, each for the fields listed.
  - The per-client rate limit (ADR-038), on the `/login`, `/setup` and `/forgot-password` screens. A `429` there shows `auth.rate_limited.with_wait` with the `Retry-After` wait, or `auth.rate_limited.no_wait` when there is none, through `rateLimitedAuthMessage` ([`src/lib/auth-rate-limit-message.ts`](src/lib/auth-rate-limit-message.ts)). That limit counts requests per client address and answers the same for existing and unknown accounts, so it reveals nothing about an account. The login, setup and recovery BFF routes (`auth/login`, `auth/register-owner`, `auth/password/recover`) pass the `429` and `Retry-After` through with `rateLimitedAuthResponse` ([`src/lib/auth-rate-limited-response.ts`](src/lib/auth-rate-limited-response.ts)). Login and recovery keep every other upstream failure on their generic copy. Setup does not: `auth/register-owner` passes the control plane's own setup error text through (for example "Setup code is invalid or expired."), and the setup screen shows it as is. That reveals nothing about accounts only because setup runs while no owner exists, so never add a `register_owner` check whose message depends on whether an identifier exists. `/settings/account` does not show the wait yet: its session routes (`auth/password/change`, `auth/recovery-codes/regenerate`) do not pass the `429` through. The per-account lockout is not a `429`: it answers like a wrong password and must stay on the generic key. Never show a lockout or "account locked" message.
  - The plain-HTTP transport refusal, decided before any credential is read: `INSECURE_TRANSPORT` (`error.code` from the login, register-owner and password-recover routes over plain HTTP from a non-loopback host; see [Plain HTTP](../../docs/security/authentication.md#plain-http)). It depends on the connection alone, so it says nothing about accounts.
- The new setup flow is strictly two screens (`step-create-account` → `step-recovery-codes`) in `src/components/setup/`. Do not re-introduce provider / GitHub / Telegram / allowed-user fields into the setup wizard; those belong to the optional post-setup checklist ([`src/components/dashboard/setup-checklist-card.tsx`](src/components/dashboard/setup-checklist-card.tsx)) and their existing drawers in `/control-plane`.
- See [`../../docs/security/authentication.md`](../../docs/security/authentication.md) for the canonical contract.

## Related guidance

- Root operational guide: [`../../CLAUDE.md`](../../CLAUDE.md).
- Architecture overview: [`../../docs/architecture/overview.md`](../../docs/architecture/overview.md).
- Design primitives live in `src/components/ui/` — the source of truth; never fork a primitive inline.
