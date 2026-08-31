# VAMS Mobile (Flutter) — Coding Agent Instructions

Context: VAMS is an existing Flask + SQLAlchemy + Jinja2 business system (multi-tenant vendor/order/invoice management). We are building a Flutter mobile companion app that talks to VAMS via a new JSON API layer. Follow these rules strictly — do not deviate without flagging it first.

---

## 1. Backend (Flask) rules

- **Never reuse existing Jinja2 template routes for mobile.** Create a separate `/api/v1/` blueprint. All mobile-facing endpoints return `jsonify()`, never rendered HTML.
- **Auth: JWT only for mobile**, via Flask-JWT-Extended. Do not use session cookies for the API layer — mobile clients can't manage cookies reliably.
  - Use short-lived access tokens + refresh tokens. Implement a `/api/v1/auth/refresh` endpoint.
  - Return 401 on expired/invalid tokens with a consistent JSON error shape: `{"error": "<code>", "message": "<human readable>"}`.
- **Version every endpoint** under `/api/v1/...`. Never change response shape of a shipped endpoint — add `/api/v2/...` instead if breaking changes are needed.
- **Do not expose more than the current mobile milestone needs.** Build endpoints for the current feature slice only (see Section 4), not the entire VAMS feature set at once.
- **Every list endpoint must support pagination** (`?page=`, `?per_page=`) and filtering by the fields staff actually filter by (status, client, date range) — do not return unbounded result sets.
- **Keep DB credentials and JWT secret in `.env`, never hardcoded, never committed.**
- **Consistent error format across all endpoints** — pick one shape now and never deviate:
  ```json
  { "success": false, "error": "validation_error", "message": "..." }
  ```

## 2. Flutter project structure — enforce this exactly

```
lib/
  core/
    api_client.dart       // dio instance, interceptors, base URL from --dart-define
    theme.dart
    router.dart            // go_router config, auth guards
    storage/               // token storage (flutter_secure_storage), local cache (hive/sqflite)
  features/
    auth/
      models/
      screens/
      providers/
    orders/
      models/
      screens/
      providers/
    invoices/
    clients/
  shared/
    widgets/               // reusable buttons, list tiles, status chips, etc.
```
Do NOT use a layer-first structure (`lib/screens/`, `lib/models/` mixed globally). Feature-first only.

## 3. Required tooling choices — do not substitute without asking

| Concern | Use | Do NOT use |
|---|---|---|
| State management | Riverpod | BLoC (overkill for this app), setState-only |
| HTTP client | `dio` | raw `http` package |
| Routing | `go_router` | Navigator 1.0 manual routes |
| Secure token storage | `flutter_secure_storage` | SharedPreferences for tokens |
| Local cache/offline reads | `hive` or `sqflite` | none (no offline handling) |
| Env config | `--dart-define` or `flutter_dotenv` | hardcoded base URLs in code |

## 4. Build order — do not skip ahead or parallelize features before the vertical slice works

1. Auth flow end-to-end: login screen → Flask `/api/v1/auth/login` → store JWT securely → attach token via dio interceptor → handle 401 → refresh flow.
2. Orders list screen: paginated fetch, loading/error/empty/data states all handled explicitly.
3. Order detail screen.
4. Only after 1–3 work cleanly end-to-end: expand to Clients, Invoices, Quotations.

Do not scaffold all feature modules up front with placeholder screens — build one full vertical slice first, then replicate the pattern.

## 5. Non-negotiable UI/UX states

Every screen that fetches data MUST explicitly handle:
- Loading state (skeleton or spinner)
- Error state (retry action, human-readable message — not raw exception text)
- Empty state (e.g. "No orders yet" — not a blank screen)
- Data state

Never leave a screen that can silently show nothing with no explanation.

## 6. Design direction

- Material 3 (`useMaterial3: true`) as the base theme, then override with VAMS brand colors.
- This is a business/data-entry app, not a consumer app: prioritize information density and scannability over decorative whitespace. Compact list tiles, not big illustrated cards.
- Bottom navigation bar, max 4–5 top-level destinations (e.g. Orders, Clients, Invoices, More).
- Status must be shown with color + icon/label together — never color alone (accessibility + scanning speed).
- Multi-step/sectioned forms for anything resembling quotation/invoice creation — not one long scrolling form.
- Consistent spacing scale: 8 / 16 / 24 px. No arbitrary padding values.
- Search/filter must be reachable in one tap from every list screen.

## 7. Common mistakes to actively avoid

- Do not hardcode the Flask VPS URL anywhere in committed code.
- Do not skip token-expiry handling — a silently-logged-out user with no explanation is a bug, not an edge case.
- Do not rebuild entire widget trees on every state change — use proper Riverpod provider scoping and `const` constructors.
- Do not test only on emulator — verify camera, file picker, and keyboard behavior on a real device before considering a feature done.
- Do not merge auth logic and business-feature logic into the same provider/file.
- Do not change an existing API response shape without bumping the API version.

## 8. Definition of done for any feature slice

- API endpoint versioned, paginated (if list), consistent error shape, JWT-protected.
- Flutter screen handles all four data states (loading/error/empty/data).
- Tested on a real device, not just emulator.
- No hardcoded URLs, secrets, or tokens in the diff.
