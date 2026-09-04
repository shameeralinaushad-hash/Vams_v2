# VAMS Mobile App — Full Test Report

**Date:** 2026-09-01
**APK Version:** 2.0.1 (version_code 6)
**Server:** https://vamsbeta.dpdns.org

---

## Test Summary

| Category | Total | Pass | Fail | Notes |
|----------|-------|------|------|-------|
| PDF Viewing | 3 | — | — | Pending |
| Auth Flow | 5 | — | — | Pending |
| API Endpoints | 12 | — | — | Pending |
| Empty States | 7 | — | — | Pending |
| SSE & Realtime | 3 | — | — | Pending |
| Pagination | 4 | — | — | Pending |
| Logout | 4 | — | — | Pending |
| Company Switch | 3 | — | — | Pending |
| Back Navigation | 3 | — | — | Pending |
| Edge Cases | 5 | — | — | Pending |
| **TOTAL** | **49** | — | — | — |

---

## 1. PDF Viewing (3 tests)

### Test 1.1: Quotation PDF opens correctly
- **Endpoint:** `GET /static/documents/company_{id}/{order_id}_{title}/Quotation_{number}.pdf`
- **How:** curl the URL returned by order detail API `quotations[].pdf_path`
- **Expected:** HTTP 200, Content-Type: application/pdf
- **Status:** ⬜

### Test 1.2: Invoice PDF opens correctly
- **Endpoint:** `GET /static/documents/company_{id}/{order_id}_{title}/Invoice_{number}.pdf`
- **How:** curl the URL returned by order detail API `invoices[].pdf_path`
- **Expected:** HTTP 200, Content-Type: application/pdf
- **Status:** ⬜

### Test 1.3: Challan PDF opens correctly
- **Endpoint:** `GET /static/documents/company_{id}/{order_id}_{title}/DeliveryChallan_{number}.pdf`
- **How:** curl the URL returned by order detail API `challans[].pdf_path`
- **Expected:** HTTP 200, Content-Type: application/pdf
- **Status:** ⬜

---

## 2. Authentication Flow (5 tests)

### Test 2.1: Login returns access + refresh tokens
- **Endpoint:** `POST /api/v1/auth/login`
- **Body:** `{"email": "admin@example.com", "password": "Admin@123"}`
- **Expected:** 200, `success: true`, `access_token` present, `refresh_token` present, `needs_company` flag
- **Status:** ⬜

### Test 2.2: Token refresh works
- **Endpoint:** `POST /api/v1/auth/refresh`
- **Header:** `Authorization: Bearer {refresh_token}`
- **Expected:** 200, `success: true`, new `access_token`
- **Status:** ⬜

### Test 2.3: Expired access token returns 401
- **Endpoint:** `GET /api/v1/auth/me` with invalid token
- **Expected:** 401, `error: "token_expired"`
- **Status:** ⬜

### Test 2.4: Company selection returns new JWT
- **Endpoint:** `POST /api/v1/auth/select-company`
- **Body:** `{"company_id": 1}`
- **Expected:** 200, new `access_token` with `company_id: 1` in claims
- **Status:** ⬜

### Test 2.5: /me returns correct user profile
- **Endpoint:** `GET /api/v1/auth/me`
- **Expected:** 200, `user` object with `name`, `email`, `role`, `company_id`
- **Status:** ⬜

---

## 3. API Endpoints (12 tests)

### Test 3.1: Dashboard loads all stats
- **Endpoint:** `GET /api/v1/dashboard`
- **Expected:** 200, `stats` with `total_orders`, `total_invoiced`, `win_rate`, `client_count`, plus `recent_orders`, `assigned_tasks`, `personal_tasks` arrays
- **Status:** ⬜

### Test 3.2: Orders list with pagination
- **Endpoint:** `GET /api/v1/orders?page=1&per_page=5`
- **Expected:** 200, `orders` array, `total`, `pages`, `current_page`
- **Status:** ⬜

### Test 3.3: Order detail with nested data
- **Endpoint:** `GET /api/v1/orders/{id}`
- **Expected:** 200, includes `quotations`, `invoices` (with `pdf_path`), `challans`, `purchase_orders`
- **Status:** ⬜

### Test 3.4: Quotation create
- **Endpoint:** `POST /api/v1/orders/{id}/quotations`
- **Body:** `{"doc_type": "quotation", "items": [{"description": "Test", "qty": 1, "unit_price": 100}]}`
- **Expected:** 201, `quotation` object with `quotation_number`, `pdf_path`
- **Status:** ⬜

### Test 3.5: Invoice create
- **Endpoint:** `POST /api/v1/orders/{id}/invoices`
- **Body:** `{"items": [{"description": "Test", "qty": 1, "unit_price": 100}]}`
- **Expected:** 201, `invoice` object with `invoice_number`, `pdf_path`
- **Status:** ⬜

### Test 3.6: Challan create
- **Endpoint:** `POST /api/v1/orders/{id}/challans`
- **Body:** `{"items": [{"description": "Test Item", "qty": 1}]}`
- **Expected:** 201, `challan` object with `challan_number`, `pdf_path`
- **Status:** ⬜

### Test 3.7: Todo toggle
- **Endpoint:** `POST /api/v1/todos/{id}/toggle`
- **Expected:** 200, `todo.status` toggles between "pending" and "done"
- **Status:** ⬜

### Test 3.8: Team task create
- **Endpoint:** `POST /api/v1/tasks/team`
- **Body:** `{"title": "Test Task", "priority": "medium"}`
- **Expected:** 201, task created
- **Status:** ⬜

### Test 3.9: Project create
- **Endpoint:** `POST /api/v1/projects`
- **Body:** `{"title": "Test Project"}`
- **Expected:** 201, project created with owner
- **Status:** ⬜

### Test 3.10: CSV export
- **Endpoint:** `GET /api/v1/accounts/expenses/export`
- **Expected:** 200, Content-Type: text/csv, starts with "Date,Scope,..."
- **Status:** ⬜

### Test 3.11: Audit log (admin)
- **Endpoint:** `GET /api/v1/audit-logs`
- **Expected:** 200, `logs` array with `action`, `entity_type`, `created_at`
- **Status:** ⬜

### Test 3.12: Notifications list
- **Endpoint:** `GET /api/v1/notifications`
- **Expected:** 200, `notifications` array
- **Status:** ⬜

---

## 4. Empty States (7 tests)

### Test 4.1: Orders list — empty company
- **How:** Switch to company with 0 orders, check screen
- **Expected:** Icon + "No orders found" text
- **Status:** ⬜

### Test 4.2: Invoices list — empty
- **Expected:** Icon + "No invoices found" text
- **Status:** ⬜

### Test 4.3: Team tasks — empty
- **Expected:** Icon + "No tasks found" text
- **Status:** ⬜

### Test 4.4: Todos — empty
- **Expected:** Text "No todos" (no icon — known inconsistency)
- **Status:** ⬜

### Test 4.5: Projects — empty
- **Expected:** Text "No projects found" (no icon — known inconsistency)
- **Status:** ⬜

### Test 4.6: Notifications — empty
- **Expected:** Icon + "No notifications" text
- **Status:** ⬜

### Test 4.7: Expenses — empty
- **Expected:** Icon + "No expenses found" text
- **Status:** ⬜

---

## 5. SSE & Realtime (3 tests)

### Test 5.1: SSE connects successfully
- **Endpoint:** `GET /api/v1/events?token={jwt}`
- **Expected:** 200, `Content-Type: text/event-stream`, keeps connection open
- **Status:** ⬜

### Test 5.2: SSE reconnects after server drops
- **How:** Kill server, wait 5s, restart — check if SSE reconnects within 3s
- **Expected:** Auto-reconnect after 3 seconds
- **Status:** ⬜

### Test 5.3: SSE with invalid token
- **Endpoint:** `GET /api/v1/events?token=invalid`
- **Expected:** 401 or connection closed, reconnect loop with null token
- **Status:** ⬜

---

## 6. Pagination (4 tests)

### Test 6.1: Orders page 1 loads
- **Endpoint:** `GET /api/v1/orders?page=1&per_page=25`
- **Expected:** 200, up to 25 orders
- **Status:** ⬜

### Test 6.2: Orders page 2 loads
- **Endpoint:** `GET /api/v1/orders?page=2&per_page=25`
- **Expected:** 200, next set of orders
- **Status:** ⬜

### Test 6.3: Last page returns fewer items
- **How:** Get `pages` from page 1, request last page
- **Expected:** Fewer than 25 items
- **Status:** ⬜

### Test 6.4: Beyond last page returns empty
- **Endpoint:** `GET /api/v1/orders?page=999&per_page=25`
- **Expected:** 200, empty `orders` array
- **Status:** ⬜

---

## 7. Logout (4 tests)

### Test 7.1: Logout clears local storage
- **How:** Call logout, check secure storage keys
- **Expected:** access_token, refresh_token, company_id, company_name, user_name, user_email, user_role all cleared. server_url preserved.
- **Status:** ⬜

### Test 7.2: API client resets after logout
- **How:** Call logout, make API call
- **Expected:** Fresh Dio instance created, no stale tokens
- **Status:** ⬜

### Test 7.3: Refresh token NOT invalidated server-side
- **How:** Logout, then use old refresh token
- **Expected:** Refresh token still works (design concern — not a bug)
- **Status:** ⬜

### Test 7.4: SSE not stopped after logout
- **How:** Logout, monitor network traffic
- **Expected:** SSE keeps reconnecting with null token every 3s (known issue)
- **Status:** ⬜

---

## 8. Company Switch (3 tests)

### Test 8.1: Switch company updates JWT
- **Endpoint:** `POST /api/v1/auth/select-company` with `company_id: 2`
- **Expected:** New access_token with `company_id: 2` in claims
- **Status:** ⬜

### Test 8.2: Dashboard reflects new company
- **How:** Switch company, call dashboard
- **Expected:** Stats change to match new company's data
- **Status:** ⬜

### Test 8.3: Invalid company_id returns error
- **Endpoint:** `POST /api/v1/auth/select-company` with `company_id: 99999`
- **Expected:** 404 or error message
- **Status:** ⬜

---

## 9. Back Navigation (3 tests)

### Test 9.1: Back on home screen exits app
- **How:** Press Android back on home tab
- **Expected:** App exits (no double-tap protection)
- **Status:** ⬜

### Test 9.2: Back on detail screen returns to list
- **How:** Navigate to order detail, press back
- **Expected:** Returns to orders list
- **Status:** ⬜

### Test 9.3: Back after tab switch exits app
- **How:** Home → Orders (bottom nav) → More (bottom nav) → press back
- **Expected:** App exits (no tab history preserved)
- **Status:** ⬜

---

## 10. Edge Cases (5 tests)

### Test 10.1: Network error shows friendly message
- **How:** Disconnect device, open dashboard
- **Expected:** "Cannot connect to server" message with retry option
- **Status:** ⬜

### Test 10.2: Order with 0 quotations/invoices/challans
- **How:** Open newly created order with no documents
- **Expected:** Empty sections with "No quotations/invoices/challans" text
- **Status:** ⬜

### Test 10.3: Large order with 50+ line items
- **How:** Create order with 50 items, view PDF
- **Expected:** PDF renders correctly, no crash
- **Status:** ⬜

### Test 10.4: Concurrent token refresh
- **How:** Fire 5 API calls simultaneously with expired token
- **Expected:** Only 1 refresh attempt, all calls retry with new token
- **Status:** ⬜

### Test 10.5: Receipt OCR with large image
- **How:** Upload 10MB photo
- **Expected:** Processes within reasonable time, no OOM crash
- **Status:** ⬜

---

## Known Issues (not bugs, design decisions)

1. **No double-tap-to-exit** on Android home screen
2. **No unsaved-changes guard** on edit screens (back button loses changes)
3. **SSE no backoff** — fixed 3s reconnect interval hammers server during outages
4. **No server-side token invalidation** on logout
5. **Todos/Projects empty states** lack icons (inconsistent with other screens)
6. **SSE token in URL query param** — appears in server logs (security concern)

---

## How to Run These Tests

### API Tests (I will execute via curl)
Tests 1.1–1.3, 2.1–2.5, 3.1–3.12, 5.1, 6.1–6.4, 7.3, 8.1–8.3

### Flutter UI Tests (manual on device)
Tests 4.1–4.7, 5.2, 7.1–7.2, 7.4, 9.1–9.3, 10.1–10.5

### What I need from you
- Confirm test credentials: `admin@example.com` / `Admin@123`
- Confirm company_id to test with
