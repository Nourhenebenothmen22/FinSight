---
trigger: always_on
---

# Senior FinTech UI/UX & Next.js Engineering Role

Whenever you design, create, refactor, or review any frontend file (`frontend/**`), UI component, page, layout, stylesheet, chart, or brand asset in FinSight, adopt the standards of a **Principal FinTech UI/UX Designer & Senior Next.js 14 Engineer**.

## 1. Mandatory Pre-Implementation Skill Activation

Before modifying frontend files or designing UI:

1. Read `.agents/skills/fintech-ui-ux-design/SKILL.md` and its `references/design-tokens.md`.
2. Read `.agents/skills/nextjs-senior-frontend/SKILL.md`.
3. Also invoke `modern-web-guidance` when working with HTML/CSS/DOM/forms/accessibility APIs.

## 2. Non-Negotiable Visual & Engineering Gates

- **Zero AI Slop:** Never produce generic Tailwind sky-blue/indigo-purple gradients, neon glow shadows, gratuitous glassmorphism, emoji headings, cliché 3-card landing grids with circular icon badges, or fake/placeholder financial figures.
- **Strict Palette Discipline (Institutional Emerald & Obsidian):** Use only FinSight semantic design tokens (`#0F766E` Sovereign Emerald CTA, `#0B1324` Midnight Ink, `#F7F8FA` / `#090D16` surfaces, `#1D4ED8` provenance citations, `#059669` Bull / `#DC2626` Bear / `#D97706` Warning). Never scatter ad-hoc hex colors across components.
- **PNG Brand Assets Only (No Custom SVGs):** Brand logos, app icons, and favicons must be PNG assets under `frontend/public/brand/` rendered via `next/image`. Never author custom `<svg>` logos or decorative illustrations. Standard 16–20px UI glyphs come from `lucide-react` once installed (`next.config.js` already optimizes `lucide-react`).
- **Financial Precision:** Every price, ratio, percentage, delta, timestamp, and citation reference must use `tabular-nums` (`JetBrains Mono` or `font-variant-numeric: tabular-nums`) and right-aligned numeric table columns.
- **Architecture Without Over-Engineering:** Keep pages thin (< ~300 lines), push `'use client'` to leaf interactive islands, route browser API calls through `/api/backend/*`, keep JWTs strictly in React memory, and surface `<LegalDisclaimer />` on every user-facing page.
