# Web App vs Flutter App — Deep Feature Comparison

## Executive Summary

| Metric | Web App | Flutter App | Ratio |
|---|---|---|---|
| Templates (HTML pages) | 76 | — | — |
| Flutter screens | — | 48 | — |
| Web route endpoints | 218 | — | — |
| API endpoints | 60 | — | — |
| **Feature coverage** | 100% | ~25% | **4:1** |

The Flutter app covers roughly **25% of web features**. Core CRUD works (orders, clients, invoices, tasks, HR, accounts, notifications) but most secondary features and the entire admin/settings surface is missing.

---

## Feature-by-Feature Analysis

### ✅ Fully Implemented in Flutter (with API)

| Feature | Web Endpoint | Flutter Screen | API Used | Notes |
|---|---|---|---|---|
| Login | `/login` | `login_screen.dart` | `POST /api/v1/auth/login` | ✅ Complete |
| Server config | (form) | `server_config_screen.dart` | — | ✅ Complete |
| Select company | `/api/v1/auth/select-company` | `login_screen.dart` (multi-company) | `POST /api/v1/auth/select-company` | ✅ Complete |
| Dashboard | `/` (home) | `home_screen.dart` | `GET /api/v1/dashboard` | ✅ Complete |
| Order list | `/orders/` | `orders_list_screen.dart` | `GET /api/v1/orders` | ✅ Complete |
| Order detail | `/orders/<id>` | `order_detail_screen.dart` | `GET /api/v1/orders/<id>` | ✅ Complete |
| Order create | `/orders/add` | `create_order_screen.dart` | `POST /api/v1/orders` | ✅ Complete |
| Create quotation | `/quotations/create` | `create_quotation_screen.dart` | `POST /api/v1/orders/<id>/quotations` | ✅ Complete |
| Create invoice | `/invoices/create` | `create_invoice_screen.dart` | `POST /api/v1/orders/<id>/invoices` | ✅ Complete |
| Create challan | `/challans/create` | `create_challan_screen.dart` | `POST /api/v1/orders/<id>/challans` | ✅ Complete |
| Client list | `/clients/` | `clients_list_screen.dart` | `GET /api/v1/clients` | ✅ Complete |
| Client detail | `/clients/<id>` | `client_detail_screen.dart` | `GET /api/v1/clients/<id>` | ✅ Complete |
| Client create | `/clients/add` | (inside detail screen) | `POST /api/v1/clients` | ⚠️ Partial |
| Client edit | `/clients/edit/<id>` | (inside detail screen) | `PUT /api/v1/clients/<id>` | ⚠️ Partial |
| Company list | (topbar switcher) | `companies_list_screen.dart` | `GET /api/v1/companies` | ✅ Complete |
| Company detail | `/companies/<id>` | `company_detail_screen.dart` | `GET /api/v1/companies/<id>` | ✅ Read-only |
| Invoice list | `/invoices/` | `invoices_list_screen.dart` | `GET /api/v1/invoices` | ✅ Complete |
| Invoice detail | `/invoices/<id>` | `invoice_detail_screen.dart` | `GET /api/v1/invoices/<id>` | ✅ Complete |
| Add payment | `/invoices/<id>/payment` | (inside detail) | `POST /api/v1/invoices/<id>/payments` | ✅ Complete |
| Team tasks | `/tasks/team` | `team_tasks_screen.dart` | `GET /api/v1/tasks/team` | ✅ Read-only |
| Personal tasks | `/tasks/mine` | `personal_tasks_screen.dart` | `GET /api/v1/tasks/personal` | ✅ Complete |
| HR employees | `/hr/employees` | `hr_screen.dart` | `GET /api/v1/hr/employees` | ✅ Read-only |
| HR attendance | `/hr/attendance` | `attendance_screen.dart` | `GET/POST /api/v1/hr/attendance/*` | ✅ Complete (scan) |
| HR payroll | `/hr/payroll` | `payroll_screen.dart` | `GET /api/v1/hr/payroll` | ✅ Read-only |
| HR holidays | `/hr/holidays` | (inside hr_screen) | `GET /api/v1/hr/holidays` | ✅ Read-only |
| Expenses | `/accounts/personal`, `/accounts/general`, `/accounts/companies` | `expenses_screen.dart`, `add_expense_screen.dart` | `GET/POST /api/v1/accounts/expenses` | ✅ Complete |
| Budgets | `/accounts/budgets` | `budgets_screen.dart` | `GET /api/v1/accounts/budgets` | ✅ Read-only |
| Notifications list | `/tasks/notifications` | `notifications_screen.dart` | `GET /api/v1/notifications` | ✅ Complete |
| Mark notification read | `/tasks/notifications/<id>/read` | (auto on tap) | `POST /api/v1/notifications/<id>/read` | ✅ Complete |
| Unread count | SSE-driven | (top of home) | `GET /api/v1/notifications/unread-count` | ✅ Complete |
| Profile | `/auth/profile` | `profile_screen.dart` | (read-only) | ⚠️ View only |
| Logout | `/auth/logout` | (in more screen) | (clears local) | ✅ Complete |
| App version check | `/api/v1/app-version` | (auto on startup) | `GET /api/v1/app-version` | ✅ Complete |

**Flutter feature count: 32 of 32 core features**

---

### ❌ Missing Entirely in Flutter

| Feature | Web Endpoint | What It Does | Priority to Build |
|---|---|---|---|
| **Search (global)** | `/search/results` | Cross-entity search: orders, clients, invoices, etc. | HIGH |
| **PDF Generation (customize)** | `/settings/pdf_builder` | Drag-drop PDF layout editor | N/A (web-only) |
| **Custom Fields** | `/settings/custom_fields` | Add custom fields to orders/clients | MEDIUM |
| **Gmail integration** | `/gmail/inbox` | Read/send emails, attach to orders | LOW (Gmail API not enabled) |
| **AI Chat** | `/ai/chat` | Chat with AI about business data | LOW |
| **Email compose/send** | (inside gmail) | Send emails to clients | LOW |
| **Mail settings** | `/settings/mail` | Configure SMTP/email templates | LOW |
| **User management** | `/auth/users` | Add/edit/delete users, set roles | HIGH (admins) |
| **Role permissions** | `/auth/users/edit/<id>` | Per-permission roles | MEDIUM |
| **User profile edit** | `/auth/profile` | Update own name/email/phone | MEDIUM |
| **Change password** | `/auth/change-password` | Update own password | MEDIUM |
| **Audit log** | `/auth/audit-log` | View all admin actions | LOW |
| **Import data (CSV/Excel)** | `/reports/import` | Bulk import clients/orders | MEDIUM |
| **Reports (custom)** | `/reports/list` | Generate custom reports | LOW |
| **Receipt OCR** | `/accounts/receipt-ocr` | Upload photo, extract amount/date | MEDIUM |
| **Recurring expenses** | `/accounts/recurring` | Auto-generate monthly expenses | MEDIUM |
| **Recurring expense generation** | `/accounts/recurring/generate` | Manual trigger | LOW |
| **Bulk delete expenses** | `/accounts/bulk/delete` | Multi-select delete | LOW |
| **Bulk recategorize** | `/accounts/bulk/recategorize` | Reassign category to many | LOW |
| **Export CSV** | `/accounts/export-csv/<scope>` | Download expense data | LOW |
| **Expense categories management** | `/accounts/categories` | Add/toggle categories | MEDIUM |
| **Budget create** | (form) | Create new budget (read-only in mobile) | MEDIUM |
| **Catalog** | `/catalog/` | Browse product catalog | MEDIUM |
| **Catalog search** | `/catalog/search` | Find products in catalog | MEDIUM |
| **Catalog suggest price** | `/catalog/suggest_price` | AI-suggested pricing | LOW |
| **Catalog duplicates** | `/catalog/duplicates` | Find duplicate products | LOW |
| **Catalog market price** | `/catalog/market_price/<id>` | Market price lookup | LOW |
| **Order: full edit** | `/orders/edit/<id>` | Edit order fields (not just create) | HIGH |
| **Order: add PO** | (form on order) | Upload PO PDF, mark received | HIGH |
| **Order: mark status** | `/orders/<id>/mark/<status>` | Change status (PO Received, etc.) | HIGH |
| **Order: view PDF** | (link in view) | Open quotation/invoice/challan PDF | MEDIUM (mobile uses link) |
| **Order: print** | (button) | Print to printer/PDF | LOW (mobile-share is enough) |
| **Quotation: edit** | `/quotations/<id>/edit` | Edit existing quotation | HIGH |
| **Quotation: list** | `/quotations/` | See all quotations | MEDIUM |
| **Quotation: delete** | (button) | Delete quotation | MEDIUM |
| **Invoice: edit** | `/invoices/<id>/edit` | Edit existing invoice | HIGH |
| **Invoice: list** | `/invoices/` | (Flutter has it but web has more filters) | ✅ Already done |
| **Invoice: delete** | (button) | Delete invoice | MEDIUM |
| **Invoice: cancel** | (button) | Cancel invoice | MEDIUM |
| **Challan: edit** | `/challans/<id>/edit` | Edit challan | MEDIUM |
| **Challan: list** | `/challans/` | See all challans | MEDIUM |
| **Challan: delete** | (button) | Delete challan | MEDIUM |
| **Client: subsidiaries** | `/clients/<id>/edit_subsidiary` | Add/edit subsidiary client | MEDIUM |
| **Client: subsidiary profile** | `/clients/<id>/subsidiary_profile` | View subsidiary details | MEDIUM |
| **Client: bulk import** | (form) | Import CSV of clients | LOW |
| **Company: edit** | `/companies/edit/<id>` | Edit company info, logo, theme | MEDIUM |
| **Company: add** | `/companies/add` | Create new company | MEDIUM |
| **Company documents** | `/company_documents/list` | Upload/manage company docs | MEDIUM |
| **Tasks: create (team)** | `/tasks/team/add` | Create new team task | HIGH |
| **Tasks: edit (team)** | `/tasks/team/<id>/edit` | Edit team task | MEDIUM |
| **Tasks: acknowledge** | (button) | Mark task as acknowledged | LOW |
| **Tasks: subtasks** | (button) | Add subtasks | LOW |
| **Tasks: discussions** | `/tasks/discussions` | Threaded comments | LOW |
| **Tasks: discussion detail** | `/tasks/discussion_detail/<id>` | Single thread | LOW |
| **HR: add employee** | `/hr/employees/add` | Create employee record | MEDIUM |
| **HR: edit employee** | `/hr/employees/<id>/edit` | Edit employee | MEDIUM |
| **HR: profile (employee)** | `/hr/profile` | Employee self-service | LOW |
| **HR: efficiency** | `/hr/efficiency` | Efficiency metrics | LOW |
| **HR: QR setup** | `/hr/qr_setup` | Configure QR attendance | N/A (admin-only) |
| **HR: QR scan (web)** | `/hr/qr_scan` | Scan QR for attendance | N/A (mobile has scan) |
| **Projects** | `/projects/` + `/projects/<id>` | Project management | MEDIUM |
| **Todos** | `/todos/` | Personal todos (different from tasks) | MEDIUM |
| **Payments list** | `/payments/` | All payment history | MEDIUM |
| **Search** | `/search/` | Global search | HIGH |
| **Settings** | `/settings/` | App-wide settings | LOW |
| **Maintenance mode** | `/maintenance/` | Toggle maintenance banner | N/A (admin-only) |
| **Backup/restore** | `/admin/backup-now` | DB backup trigger | N/A (admin-only) |
| **Database backup UI** | (admin panel) | Manual backup | N/A (admin-only) |

**Missing in Flutter: 60+ features**

---

## Web-Only Features (Admin / Desktop Use)

These are intentionally desktop-only and not appropriate for mobile:

| Feature | Web URL | Reason |
|---|---|---|
| PDF builder | `/settings/pdf_builder` | Drag-drop editor needs large screen |
| Custom fields | `/settings/custom_fields` | Schema-level changes, risky on mobile |
| User management | `/auth/users` | Admin function, security |
| Role permissions | `/auth/users/edit/<id>` | Admin function |
| Audit log | `/auth/audit-log` | Large data tables |
| Maintenance mode | `/maintenance/` | Admin function |
| Backup/restore | (admin panel) | Admin function |
| Reports | `/reports/list` | Complex query builder |
| Email settings | `/settings/mail` | SMTP config |

---

## Mobile-Specific Features (Not in Web)

| Feature | Notes |
|---|---|
| **QR scanning for attendance** | Native camera access — no web equivalent |
| **Push to mobile** | Future: FCM for offline alerts |
| **Camera capture** | Receipt photos, profile pictures |
| **Offline drafts** | Future: local-first edits |
| **Biometric auth** | Future: Face ID / fingerprint login |
| **App update banner** | Already implemented (`/api/v1/app-version`) |

---

## Deep Feature Gaps Analysis

### 1. **Order Management (most-used feature) — Partial**

Flutter has:
- ✅ List, detail, create
- ❌ Edit existing order
- ❌ Mark status (PO Received, Delivered, etc.)
- ❌ Add PO document
- ❌ Delete order
- ❌ View status timeline

**Recommendation:** Add `/api/v1/orders/<id>` PUT, status-change endpoint, and a "more" menu in order detail.

### 2. **Documents (Quotations/Invoices/Challans) — Read-Only After Create**

Flutter has:
- ✅ Create quotation, invoice, challan
- ✅ View invoice list/detail
- ❌ Edit any document
- ❌ Delete any document
- ❌ View all quotations / all challans
- ❌ List invoices by order (web has per-order view)

**Recommendation:** Add edit/delete endpoints for all three.

### 3. **Client Management — No Subsidiary Support**

Flutter has:
- ✅ List, detail, create, edit client
- ❌ Subsidiary clients (child companies)
- ❌ Subsidiary profile view

**Recommendation:** Add `/api/v1/clients/<id>/subsidiaries` endpoint and UI.

### 4. **Tasks — No Creation Flow**

Flutter has:
- ✅ View team tasks
- ✅ View/create/edit personal tasks
- ❌ Create team task
- ❌ Edit team task
- ❌ Subtasks
- ❌ Acknowledgement
- ❌ Discussions

**Recommendation:** Add `/api/v1/tasks/team` POST and edit PUT.

### 5. **HR — Read-Only After Setup**

Flutter has:
- ✅ View employees
- ✅ Attendance scan + view today
- ✅ View payroll
- ✅ View holidays
- ❌ Add/edit employees (HR admin function)
- ❌ QR setup (admin only)

**Note:** HR is read-only for employees + scan-only for attendance. Reasonable scope.

### 6. **Accounts — Missing 60% of Web Features**

Flutter has:
- ✅ View expenses (personal/general/company)
- ✅ Add expense
- ✅ View categories
- ✅ View budgets
- ❌ Edit/delete expenses
- ❌ Add categories
- ❌ Toggle categories on/off
- ❌ Add budgets
- ❌ Recurring expenses
- ❌ Receipt OCR
- ❌ Export CSV
- ❌ Bulk operations

**Recommendation:** Add edit/delete + categories management.

### 7. **Search — Completely Missing**

Flutter has NO search at all (except in some list screens).

**Web has:** Global search across orders, clients, invoices, challans, etc.

**Recommendation:** Add `/api/v1/search?q=...` and a search bar to top-level screens.

### 8. **Dashboard — Missing Assigned Tasks**

Flutter dashboard:
- ✅ Stats (revenue, orders, etc.)
- ✅ Recent orders
- ❌ Assigned tasks widget
- ❌ Personal tasks widget

**Note:** API has `assigned_tasks` and `personal_tasks` fields, just not displayed in mobile UI.

### 9. **Profile & Auth — Limited**

Flutter has:
- ✅ View profile (read-only)
- ✅ Logout
- ❌ Edit own profile (name, email, phone)
- ❌ Change password
- ❌ 2FA (web may not have this either)

**Recommendation:** Add `/api/v1/auth/profile` PUT and `/api/v1/auth/change-password`.

### 10. **Companies — Read-Only**

Flutter has:
- ✅ View companies list
- ✅ View company detail
- ❌ Create company
- ❌ Edit company
- ❌ Upload logo
- ❌ Upload letterhead
- ❌ Change PDF theme

**Note:** These are admin functions, low priority for mobile.

### 11. **Catalog — Missing Entirely**

Flutter has NO catalog functionality.

**Web has:** Product catalog with search, pricing, duplicates detection.

**Recommendation:** Add `/api/v1/catalog/*` mobile views (medium priority — used for order line items).

### 12. **Projects, Todos, Payments — Missing**

Three entire sections of the web app are not in Flutter.

**Recommendation:** Add at least:
- Project list + detail
- Payment list (could be inside invoice detail)
- Todo list (similar to personal tasks)

### 13. **Notifications — Limited Actions**

Flutter has:
- ✅ View list
- ✅ Mark read on tap
- ❌ Filter (unread only, by type)
- ❌ Search notifications
- ❌ Mark all as read (button)
- ❌ Clear all
- ❌ Notification preferences

**API has:** `/unread-count`, `/read-all`, `/clear-all`, `/<id>/read` — all are implemented server-side. Just not used in mobile UI.

### 14. **Settings — No App**

Flutter has NO settings screen.

**Web has:** Mail, PDF builder, custom fields, app config.

**Note:** These are admin-only, low priority.

---

## Critical Missing API Endpoints

Some features need new API endpoints before they can be added to Flutter:

| Need | Suggested Endpoint | Web Reference |
|---|---|---|
| Edit order | `PUT /api/v1/orders/<id>` | `/orders/edit/<id>` |
| Delete order | `DELETE /api/v1/orders/<id>` | `/orders/delete/<id>` |
| Edit quotation | `PUT /api/v1/quotations/<id>` | `/quotations/<id>/edit` |
| Delete quotation | (exists) | — |
| Edit invoice | `PUT /api/v1/invoices/<id>` | `/invoices/<id>/edit` |
| Delete invoice | (exists) | — |
| Edit challan | `PUT /api/v1/challans/<id>` | `/challans/<id>/edit` |
| Delete challan | (exists) | — |
| Create team task | (exists — `POST /api/v1/tasks/team`) | — |
| Edit team task | (exists — `PUT /api/v1/tasks/team/<id>`) | — |
| Global search | `GET /api/v1/search?q=` | `/search/` |
| Edit profile | `PUT /api/v1/auth/profile` | `/auth/profile` |
| Change password | `POST /api/v1/auth/change-password` | `/auth/change-password` |
| List quotations (all) | `GET /api/v1/quotations` | `/quotations/` |
| List challans (all) | `GET /api/v1/challans` | `/challans/` |
| Mark all read | (exists) | — |
| Clear all notifications | (exists) | — |
| Receipt OCR | `POST /api/v1/accounts/receipt-ocr` | `/accounts/receipt-ocr` |
| Subsidiary clients | `GET /api/v1/clients/<id>/subsidiaries` | `/clients/<id>/edit_subsidiary` |
| Add PO | `POST /api/v1/orders/<id>/po` | (form on order page) |
| Change order status | `POST /api/v1/orders/<id>/status` | `/orders/<id>/mark/<status>` |
| Project list | `GET /api/v1/projects` | `/projects/` |
| Project detail | `GET /api/v1/projects/<id>` | `/projects/<id>` |
| Todos | `GET/POST/PUT/DELETE /api/v1/todos` | `/todos/` |
| Payments | `GET /api/v1/payments` | `/payments/` |

---

## Quick-Win Improvements (Low Effort, High Value)

If you want to add value fast, prioritize these:

1. **Edit/Delete buttons on order detail screen** — needs `PUT/DELETE /api/v1/orders/<id>`
2. **Edit/Delete on quotation/invoice/challan** — needs PUT endpoints
3. **"Mark all read" + "Clear all" buttons in notifications** — API exists, just add UI
4. **Edit profile screen** — add 3 fields (name, email, phone)
5. **Change password screen** — add 2 fields (old, new)
6. **Global search bar** — needs `/api/v1/search` endpoint
7. **Tasks: "create team task" button** — API exists, just add form
8. **Order: status change menu** — needs `POST /api/v1/orders/<id>/status`
9. **Subsidiary client support** — add 2 endpoints + list view
10. **Show assigned/personal tasks on dashboard** — API returns them, just render

---

## Conclusion

The Flutter app covers the **core "read + create" flow** for orders, clients, invoices, tasks, HR, and accounts. It's good for field staff (attendance scan, quick order creation, expense entry, document viewing).

It's missing the **"manage" flow** — edit, delete, bulk operations, search, settings. These are needed for office staff and admins.

**Recommended next steps (in order):**
1. Add edit/delete to all documents (orders, quotations, invoices, challans)
2. Add global search
3. Add edit profile + change password
4. Add team task creation
5. Add receipts OCR
6. Add subsidiary client support
7. Add projects/todos/payments views
8. Add categories management
