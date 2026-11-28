---
name: fintech-ui-ux-design
description: Enforces FinSight's Institutional Emerald & Obsidian design system, anti-AI-slop standards, button/form states, tabular financial typography, PNG brand assets (no custom SVGs), and Recharts visualization architecture. Use whenever designing, building, or reviewing UI, pages, components, styles, themes, charts, or branding in FinSight.
---

# FinSight FinTech UI/UX Design System

## Objective
Deliver an institutional-grade financial analysis UI (benchmark: Stripe, Linear, Koyfin, Carta) with sharp visual hierarchy, calm analytical density, WCAG AA contrast, and zero generic AI-generated clichés.

For exact hex values, CSS custom properties, spacing scale, and Tailwind mappings, read [design-tokens.md](./references/design-tokens.md).

## 1. Anti-AI-Slop Checklist (Reject Before Shipping)
- **No AI color clichés:** Ban violet/indigo/sky-blue gradients (`from-blue-500 to-purple-600`), neon drop shadows (`shadow-blue-500/20`), and decorative pulsing/bouncing badges.
- **No filler chrome:** Depth comes from surface luminance shifts and crisp `1px` hairline borders (`#E2E8F0` light / `#1F2937` dark), not heavy shadows or glassmorphism.
- **No cliché landing grids:** Never default to centered 3-column feature boxes with generic circular icons and marketing buzzwords; anchor public views around product clarity, real sample workflows, and clear CTAs.
- **No emoji headings:** Never put emojis inside page titles, card headers, navigation links, or buttons.
- **No fake numbers:** Never populate KPI cards, charts, or tables with invented financial data; show explicit empty, loading-skeleton, or partial-failure states instead.

## 2. Semantic Color Discipline (`Institutional Emerald & Obsidian`)
Keep color meanings mutually exclusive so analysts never misread signals:
- **Primary Action (`#0F766E` light / `#14B8A6` dark):** Primary buttons, active navigation indicators, focus rings, primary chart line.
- **Authority Ink (`#0B1324` light / `#F8FAFC` dark):** Headings, primary values, strong structural borders.
- **Bull / Approved (`#059669` / `#34D399`):** Positive financial deltas and Critic-approved badges only.
- **Bear / Risk / Rejected (`#DC2626` / `#F87171`):** Negative deltas, risk alerts, Critic rejections, and destructive actions only.
- **Warning / Revision (`#D97706` / `#FBBF24`):** Pending Critic revisions, degraded workers, near-quota indicators.
- **Provenance / Citation (`#1D4ED8` / `#60A5FA`):** Reserved exclusively for source page badges (`[AR 2025 · p. 42]`) and external provenance links.

## 3. Typography & Numeric Precision
- **Display & UI Sans:** `Plus Jakarta Sans` or `Inter` (`tracking-[-0.025em]` on display headings, `leading-relaxed` on analytical prose capped at `max-w-3xl`).
- **Financial & Citation Mono:** `JetBrains Mono` with `font-variant-numeric: tabular-nums` (`tabular-nums`) on all prices, currencies, percentages, deltas, ratios, dates, tickers, and page references.
- **Financial Tables:** Sticky header, crisp horizontal row dividers (`1px`), left-aligned labels, **right-aligned `tabular-nums`** numeric columns, subtle hover row tint.

## 4. Buttons, Forms & Interactive States
- **Consistent Radius & Height:** Standardize on `rounded-lg` (`8px`) for buttons/inputs and `rounded-xl` (`12px`) for containers. Button heights: `36px` (compact toolbar), `40px` (standard desktop), `44–48px` (auth/primary/touch CTA).
- **Button Hierarchy:**
  - *Primary:* Solid `#0F766E` (`hover:#115E59`), white text, subtle `active:scale-[0.99]`.
  - *Secondary:* Crisp surface background, `1px solid #CBD5E1` border (`dark:#334155`), high-contrast ink.
  - *Ghost:* Transparent for secondary nav/inline controls.
  - *Danger:* `#DC2626` reserved for destructive actions with confirmation where irreversible.
- **Required States:** Every interactive control must define hover, `focus-visible` (`2px` ring + `2px` offset), disabled (`opacity-50 cursor-not-allowed`), and async busy (`aria-busy`, inline spinner without layout shift).
- **Forms & Error UX:** Validate with Zod on blur + submit, wire `aria-invalid` and `aria-describedby`, and display `429 Retry-After` wait guidance cleanly inside `role="alert"` banners.
- **Loading / Empty / Error:** Use geometry-matching `Skeleton` blocks instead of blank full-screen spinners whenever layout structure is known.

## 5. Brand Logo (PNG Only) & Icons
- **Logo & App Icons:** Strictly **PNG** assets stored under `frontend/public/brand/` and rendered with `next/image` (`<BrandLogo />`). Reference PNG icons in `manifest.json` and `layout.tsx` metadata. Never create `.svg` logo files or bespoke inline `<svg>` brand graphics/illustrations.
- **UI Micro-Icons:** Use `lucide-react` (`16px`–`20px`, uniform `strokeWidth={1.75}`) rather than hand-written inline `<svg>` paths.

## 6. Financial Charts Architecture (`Recharts`)
Build typed chart wrappers in `frontend/src/components/charts/`:
- Wrap `<ResponsiveContainer>` in a fixed-height container (`min-h-[260px]`) with accessible `aria-label`.
- Use horizontal dashed hairlines only (`strokeDasharray="3 3"`, `#E2E8F0` light / `#1F2937` dark); hide vertical gridlines and heavy axis spines.
- Use ordered series colors from [design-tokens.md](./references/design-tokens.md) and soft area fill gradients (`0.18 → 0.0` opacity).
- Always attach a custom `<FinancialChartTooltip />` (`tabular-nums` values + period delta) instead of Recharts' default box.
- Pair every financial chart with a top KPI summary strip and a bottom provenance citation line (`Source: ...`).

## 7. Design Verification Checklist
Before completing any UI change:
1. Verify light and dark modes meet WCAG AA contrast (`>= 4.5:1` text, `>= 3:1` UI borders/controls).
2. Verify responsive behavior at `375px` mobile and `1280px+` desktop with zero horizontal overflow.
3. Confirm no custom inline `<svg>` logos/illustrations were added and PNG brand assets render cleanly.
4. Run `npm run format:check`, `npm run lint`, `npm run typecheck`, and `npm test`.
