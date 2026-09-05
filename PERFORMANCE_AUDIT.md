# Performance Audit — VAMS Business System

**Date:** 2026-09-05
**Status:** In Progress (Phase 1 starting)

---

## Executive Summary

| Layer | Critical | High | Medium | Total |
|-------|----------|------|--------|-------|
| SSE/Real-time | 2 | 3 | 4 | 9 |
| Database | 3 | 10 | 6 | 19 |
| Frontend/Assets | 3 | 4 | 3 | 10 |
| PDF Generation | 0 | 3 | 4 | 7 |
| ML Extraction | 0 | 3 | 5 | 8 |
| **Total** | **8** | **23** | **22** | **53** |

---

## CRITICAL Issues (Fix Immediately)

### 1. SSE Events Lost with Multiple Workers
**Files:** `sse.py:12`, `wsgi.py:5`
**Impact:** 75% of clients miss real-time updates
**Root Cause:** `_connections` dict is per-process. With 4 workers, events pushed from one worker only reach clients on that same worker.
**Fix:** Use Redis Pub/Sub as shared message bus, or set `UVICORN_WORKERS=1`.

### 2. Order Model Cascading `lazy="selectin"`
**File:** `models.py:209-238`
**Impact:** Every Order load triggers ~15 SQL queries. Loading 100 orders = ~1,500 queries.
**Root Cause:** 8 relationships all use `lazy="selectin"`, cascading into child collections.
**Fix:** Change to `lazy="noload"` or `lazy="raise"`, use explicit loading in routes.

### 3. HR N+1 Queries
**File:** `routes/hr.py`
**Impact:** 80-120 queries per page for 20 employees.
**Root Cause:** Employee list, efficiency page, payroll generation all loop with 2-5 queries per employee.
**Fix:** Batch with single grouped SQL queries.

### 4. AI Context Builder Loads All Data into Python
**File:** `routes/ai.py:30-42`
**Impact:** All orders/invoices loaded with cascading selectin, counted in Python.
**Fix:** Use SQL `COUNT`/`SUM` aggregations.

### 5. Full Page Re-fetch on Every SSE Refresh Event
**File:** `templates/base.html:2210-2234`
**Impact:** Every entity change triggers full page re-render for ALL connected users.
**Fix:** Debounce (300ms), use targeted JSON updates instead of full HTML re-fetch.

### 6. No Pagination on Major List Pages
**Impact:** expenses, catalog, companies, orders, tasks, projects all load ALL rows.
**Fix:** Add `.paginate()` or `.limit()` to all list queries.

### 7. Invoice/PurchaseOrder/DeliveryChallan Cascading Selectin
**File:** `models.py:446-449, 305`
**Impact:** Loading any Invoice cascades into PO, line_items, payments, credit_notes recursively.
**Fix:** Change to `lazy="select"`, load explicitly where needed.

### 8. Accounts Dashboard 6-Month Loop
**File:** `routes/accounts.py:290-313`
**Impact:** 12 queries (6 months x 2 entity types) that could be 2 grouped SQL queries.
**Fix:** Use SQL GROUP BY for monthly aggregation.

---

## HIGH Issues (Fix This Week)

### Database
9. `_get_or_create_catalog_item` commits in loop (`routes/api_invoices.py:337-344`)
10. Reports loads ALL invoices (`routes/reports.py:52-55`)
11. Client profile loads ALL clients (`routes/clients.py:144`)
12. Multiple sequential commits in order creation (`routes/orders.py:128-146`)
13. Missing indexes on `Invoice.status`, `TeamTask.status`, `Expense.expense_date`
14. `Project.progress_pct()`/`health()` N+1 (`models.py:1024-1061`)
15. `auto_archive_purge` runs on every page load (`routes/tasks.py:672-686`)

### SSE/Real-time
16. Global lock held during full connection iteration (`sse.py:43-48`)
17. DB query on every 5s keepalive per connection (`sse.py:73-82`)
18. `run_in_executor` consumes threads despite "async" label (`sse.py:102-105`)
19. No connection limits on SSE endpoints (`asgi.py:24-38`)
20. Unbounded thread spawning in background.py (`background.py:29-30`)

### Frontend
21. Chart.js loaded TWICE on dashboard (`base.html` + `dashboard.html`)
22. 55KB inline CSS in base.html, 29KB in dashboard.html (unminified)
23. 28KB inline JS in base.html (unminified)
24. No `defer` on render-blocking scripts

### PDF Generation
25. PDF generation blocks HTTP requests on create (`routes/quotations.py:411`, `invoices.py:160`, `challans.py:144`)
26. Bulk salary slip generation synchronous O(N) disk I/O (`routes/hr.py:800-825`)
27. User photos not downscaled before embedding (`quotation_template.py:290-313`)

### ML Extraction
28. Extraction routes block Flask workers (no async/background)
29. `_EXTRACTION_LOCK` defined but never acquired (`tender_extractor.py:106`)
30. Entire PDF read into memory 4-6 times (`tender_extractor.py:219-2240`)

---

## MEDIUM Issues (Fix This Month)

### Database
31. Notification.send() commits per call (`models.py:941-944`)
32. Projects N+1 on ProjectUpdate (`routes/projects.py:62-73`)
33. `Employee.get_paid_leave_stats()` queries in loop (`models.py:737-763`)
34. HR monthly attendance 24 queries (`routes/hr.py:328-337`)
35. Catalog O(n^2) duplicate detection (`routes/catalog.py:105-119`)
36. User.query.all() in notification loops (`routes/hr.py:277,648`)

### SSE/Real-time
37. `_event_id` race condition (`sse.py:14,39-40`)
38. Unbounded queue with no backpressure (`sse.py:20,46`)
39. No uvicorn keepalive timeout (`asgi.py:75`)
40. Redundant DB query in emit_notification_update (`socket_events.py:22-34`)
41. No debounce on refresh handler (`base.html:2239-2241`)
42. Double broadcast per mutation (all route files)

### Frontend
43. No Gzip/Brotli compression middleware
44. No `integrity` (SRI) on CDN scripts
45. Mermaid.js ~2MB loaded on My Space page

### PDF Generation
46. NumberedCanvas stores full page state dicts (`shared.py:84-94`)
47. Logo re-opened with PIL on every page (`shared.py:141-162`)
48. Statement regenerated on every download (`routes/clients.py:245`)
49. Salary slips regenerated on every download (`routes/hr.py:793`)

### ML Extraction
50. No timeout on AI API calls or Tesseract
51. Groq client created per-request (no singleton)
52. No content-hash caching of extraction results
53. Duplicate JSON parsing logic (3x copy-paste)
54. Hardcoded `time.sleep()` between AI chunks

---

## Fix Phases

### Phase 1: SSE Multi-Worker Fix
**Priority:** CRITICAL
**Effort:** 2-4 hours
**Items:** #1, #7
**Approach:** Replace in-memory `_connections` with Redis Pub/Sub for cross-worker event broadcasting. Each worker subscribes to a Redis channel and forwards events to local SSE queues.

### Phase 2: DB Relationship Fixes
**Priority:** CRITICAL
**Effort:** 3-5 hours
**Items:** #2, #7, #9, #13
**Approach:** Change Order/Invoice/PO/DeliveryChallan relationships from `lazy="selectin"` to `lazy="noload"`. Add explicit `selectinload()`/`joinedload()` in route functions. Add missing indexes.

### Phase 3: Dashboard/SQL Optimizations
**Priority:** CRITICAL
**Effort:** 2-3 hours
**Items:** #4, #8, #10, #38
**Approach:** Replace Python-side aggregations with SQL GROUP BY/SUM. Fix accounts dashboard loop. Optimize reports page.

### Phase 4: HR Batch Queries
**Priority:** CRITICAL
**Effort:** 2-3 hours
**Items:** #3, #34, #33, #36
**Approach:** Batch employee attendance queries with single grouped SQL. Fix payroll generation N+1. Fix notification loops.

### Phase 5: Frontend Compression
**Priority:** MEDIUM
**Effort:** 1-2 hours
**Items:** #21, #22, #23, #24, #43
**Approach:** Add flask-compress. Remove duplicate Chart.js. Add defer to scripts. Extract inline CSS/JS to external files.

### Phase 6: Pagination
**Priority:** MEDIUM
**Effort:** 2-3 hours
**Items:** #6, #11, #14, #15
**Approach:** Add `.paginate()` to expenses, catalog, companies, orders, tasks, projects list pages. Add search/autocomplete for dropdowns.

### Phase 7: Background Tasks
**Priority:** MEDIUM
**Effort:** 3-5 hours
**Items:** #20, #25, #28, #29
**Approach:** Use bounded ThreadPoolExecutor for PDF generation and ML extraction. Add task tracking and cancellation support.

### Phase 8: ML Extraction Memory
**Priority:** MEDIUM
**Effort:** 2-3 hours
**Items:** #29, #30, #50, #51, #52
**Approach:** Read file once at top of extraction. Add timeouts to AI API calls. Cache Groq client. Add content-hash caching.

---

## Progress Log

| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2026-09-05 | Phase 1 | Done | Redis/in-memory SSE dual mode, bounded ThreadPoolExecutor, frontend debounce, Flask-Compress |
| 2026-09-05 | Phase 2 | Done | Changed Order/Invoice/DeliveryChallan/PurchaseOrder to lazy=noload, added selectinload in 12 route files |
| 2026-09-05 | Phase 3 | Done | AI context builder SQL aggregations, accounts dashboard 6-month loop→2 SQL queries, reports SQL aggregations, SSE backpressure already in Phase 1 |
| 2026-09-05 | Phase 4 | Done | HR efficiency page: 6 queries/employee→2 batch SQL. Payroll generation: 5 queries/employee→3 batch SQL |
| 2026-09-05 | Phase 5 | Done | Removed 12 duplicate Chart.js CDN includes, added defer to 4 scripts (Chart.js, Bootstrap, SortableJS, Mermaid) |
| 2026-09-05 | Phase 6 | Done | Added pagination to catalog list (per_page=50), converted 6 Python sum→SQL SUM in accounts |
| 2026-09-05 | Phase 7 | Done | Made PDF generation non-blocking for all create/edit routes (quotations, invoices, challans, API routes) using run_in_background() |
| 2026-09-05 | Phase 8 | Done | Singleton Groq client, 60s API timeout for Groq, _EXTRACTION_LOCK acquired in all extraction routes, gc.collect() for PDF/base64 cleanup |
