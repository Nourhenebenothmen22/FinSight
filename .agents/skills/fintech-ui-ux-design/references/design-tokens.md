# FinSight Design Tokens — Institutional Emerald & Obsidian (Option 1)

Use these canonical tokens when updating `frontend/src/app/globals.css` and `frontend/tailwind.config.ts`. Never hard-code arbitrary hex colors inside feature components.

## 1. Color Palette (Light & Dark)

| Role | CSS Variable | Light Value | Dark Value | Notes |
|---|---|---|---|---|
| Canvas background | `--background` | `#F7F8FA` (`220 23% 97%`) | `#090D16` (`220 42% 6%`) | Global page canvas |
| Card / Surface | `--card` | `#FFFFFF` (`0 0% 100%`) | `#111827` (`221 39% 11%`) | Primary analytical panels |
| Subtle / Elevated | `--muted` | `#EEF2F6` (`210 29% 95%`) | `#1E293B` (`217 33% 17%`) | Table headers, hover, active pills |
| Hairline border | `--border` | `#E2E8F0` (`214 32% 91%`) | `#1F2937` (`215 28% 17%`) | 1px structural separation |
| Input border | `--input` | `#CBD5E1` (`213 27% 84%`) | `#334155` (`215 25% 27%`) | Form control outlines |
| Primary ink | `--foreground` | `#0B1324` (`221 53% 9%`) | `#F8FAFC` (`210 40% 98%`) | Headings & primary body |
| Muted ink | `--muted-foreground` | `#475569` (`215 19% 35%`) | `#94A3B8` (`215 20% 65%`) | Secondary labels, axis ticks |
| Brand CTA | `--primary` | `#0F766E` (`175 77% 26%`) | `#14B8A6` (`173 80% 40%`) | Primary buttons & focus ring |
| Brand CTA hover | `--primary-hover` | `#115E59` | `#0D9488` | Hover state for primary actions |
| Brand CTA ink | `--primary-foreground` | `#FFFFFF` | `#042F2E` | High-contrast text on primary |
| Focus ring | `--ring` | `#0F766E` | `#2DD4BF` | Keyboard focus-visible outline |

### Semantic Finance & Provenance Tokens

| Meaning | Light Hex | Dark Hex | Light Subtle Bg | Dark Subtle Bg |
|---|---|---|---|---|
| **Bull / Positive / Approved** | `#059669` | `#34D399` | `#ECFDF5` | `rgba(6, 78, 59, 0.35)` |
| **Bear / Risk / Rejected** | `#DC2626` | `#F87171` | `#FEF2F2` | `rgba(127, 29, 29, 0.35)` |
| **Warning / Revision** | `#D97706` | `#FBBF24` | `#FFFBEB` | `rgba(120, 53, 15, 0.35)` |
| **Citation / Provenance** | `#1D4ED8` | `#60A5FA` | `#EFF6FF` | `rgba(30, 58, 138, 0.35)` |

### Emerald Brand Scale (`primary.*` in Tailwind)

```ts
primary: {
  50:  '#F0FDFA',
  100: '#CCFBF1',
  200: '#99F6E4',
  300: '#5EEAD4',
  400: '#2DD4BF',
  500: '#14B8A6',
  600: '#0D9488',
  700: '#0F766E', // Light primary CTA
  800: '#115E59', // Light primary CTA hover
  900: '#134E4A',
  950: '#042F2E',
}
```

## 2. Recharts Series Order

1. `#0F766E` (`#14B8A6` dark) — Primary company / portfolio series
2. `#1D4ED8` (`#60A5FA` dark) — Benchmark / sector peer
3. `#D97706` (`#FBBF24` dark) — Margin / forecast / threshold
4. `#64748B` (`#94A3B8` dark) — Historical baseline
5. `#BE123C` (`#FB7185` dark) — Drawdown / volatility / risk

## 3. Spacing, Radius & Layout Rhythm

- **8pt scale:** `4px (1)`, `8px (2)`, `12px (3)`, `16px (4)`, `24px (6)`, `32px (8)`, `48px (12)`, `64px (16)`.
- **Container widths:**
  - Auth / single-focus flow: `max-w-md` (`448px`)
  - Analytical report prose: `max-w-3xl` (`768px`)
  - Workspace / dashboard / comparison views: `max-w-7xl` (`1280px`)
- **Border radius:**
  - Inputs, buttons, table badges: `rounded-lg` (`8px`) / `rounded-md` (`6px`)
  - Cards & modals: `rounded-xl` (`12px`)
- **Typography utilities:**
  - Always apply `tabular-nums` (`font-variant-numeric: tabular-nums`) on financial figures and tables.
  - Display hero headline: `text-3xl sm:text-5xl font-semibold tracking-[-0.025em]`.
  - Section title: `text-xl sm:text-2xl font-semibold tracking-[-0.015em]`.
  - Card / panel label: `text-xs font-semibold uppercase tracking-wider text-muted-foreground`.
