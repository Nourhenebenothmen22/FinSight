---
name: nextjs-senior-frontend
description: Guides senior Next.js 14 App Router architecture, Server/Client Component boundaries, feature-based modularity, performance, SSE progress streaming, accessibility, and security for FinSight without over-engineering. Use when creating or refactoring pages, layouts, providers, hooks, API clients, or components in frontend/.
---

# Senior Next.js 14 Frontend Engineering

## Objective
Build fast, accessible, type-safe, maintainable Next.js 14 App Router code tailored to FinSight (`frontend/`) with clean boundaries and zero unnecessary abstractions.

## 1. Server vs. Client Boundaries
- Default to **Server Components** for `layout.tsx`, metadata, SEO, and static page shells; push `'use client'` strictly down to leaf interactive islands (forms, chart containers, workspace switchers, SSE live progress panels).
- Never duplicate route-level business logic or data normalization across `useEffect` and callbacks; extract one focused helper or hook per concern.
- Keep route `page.tsx` files concise (< ~300 lines). When a page handles multiple sections (e.g. members + invitations + audit logs + settings), split into cohesive feature components rather than building an 800-line monolith.

## 2. Pragmatic Folder Structure (No Over-Engineering)
Organize `frontend/src/` incrementally as features F3–F18 arrive:
- `src/app/` — App Router pages, layouts, and `/api/backend/[...path]/route.ts` BFF proxy.
- `src/components/ui/` — Small reusable primitives (`Button`, `Card`, `Badge`, `Alert`, `Skeleton`, `DataTable`). Build only primitives actually used; do not install heavy component frameworks needlessly.
- `src/components/brand/` — `<BrandLogo />` (`next/image` PNG) and `<LegalDisclaimer />`.
- `src/components/charts/` — Typed Recharts wrappers (`<FinancialChartTooltip />`, trend/comparison charts).
- `src/components/layout/` — `Navbar` and workspace `AppShell`.
- `src/components/auth/` — `AuthProvider`, `WorkspaceProvider`, auth UI.
- `src/lib/` — `api.ts` (typed client + single-flight refresh), domain API modules (`auth.ts`, `orgs.ts`), `formatters.ts` (currency, percent, compact numbers, UTC dates), and Zod schemas under `lib/validations/`.

Avoid Redux, Zustand, or redundant repository abstractions while React Context + typed `fetch` wrappers meet the requirement cleanly.

## 3. Performance & Asset Discipline
- **Fonts:** Load UI sans (`Plus Jakarta Sans` or `Inter`) and `JetBrains Mono` via `next/font/google` with `display: 'swap'` and CSS variables in `src/app/layout.tsx`.
- **Images:** Render all PNG logos and raster media through `next/image` with explicit `width` and `height` to eliminate layout shift (CLS).
- **Code Splitting:** Lazy-load heavy below-the-fold `Recharts` dashboards or report/PDF previewers with `next/dynamic` (`ssr: false` only when browser APIs require it) alongside matching `<Skeleton />` fallbacks.
- **StrictMode Safety:** Deduplicate concurrent refresh/fetch effects via `useRef` single-flight promises (as in `AuthProvider`) and guard async state updates against unmount with cancellation flags or `AbortController`.

## 4. Security, BFF Proxy & Streaming (SSE)
- Route all browser API calls through `/api/backend/*` (`src/lib/api.ts`) so `HttpOnly` refresh cookies (`finsight_refresh_token`), `X-Tenant-ID`, `Retry-After`, and `X-Request-ID` stay consistent on a single origin.
- Store JWT access tokens strictly in React memory (`useRef` / `useState`), never `localStorage` or `sessionStorage`.
- **Untrusted Content:** Treat PDF extracts, filenames, tickers, news summaries, and LLM markdown outputs as untrusted data — render safely as React nodes or sanitized markdown; never use `dangerouslySetInnerHTML`, and validate URLs (`http:`/`https:` only) before rendering source links.
- **SSE Progress (F5 / F11):** Consume streaming analysis progress with `AbortController` cleanup on unmount, reconnect/backoff handling, and visible partial-failure warnings rather than silent failure.

## 5. Accessibility & Compliance
- Enforce semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`), single logical `<h1>` per page, keyboard focus management on validation errors, and `role="status"` / `role="alert"` live regions.
- Ensure every interactive form/nav control has at least a `44px` hit target on mobile (`min-h-[44px]`).
- Include `<LegalDisclaimer />` on every public, authentication, workspace, analysis, and report view.

## 6. Verification
Before concluding any frontend change:
1. Run inside `frontend/` (or `docker compose exec -T frontend`):
   - `npm run format:check`
   - `npm run lint`
   - `npm run typecheck`
   - `npm test`
2. Verify production compilation (`npm run build` or `docker build --target production ./frontend`) when changing layouts, fonts, assets, Tailwind config, or routes.
