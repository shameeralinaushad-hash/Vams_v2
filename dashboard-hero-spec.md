# Dashboard Hero Section — Build Spec

## Goal
Add a hero section above the existing `.zentra-header` in `dashboard.html` (Overview page). It has two parts:
1. A greeting bar with an "Entity Profile" link
2. An "Important Actions" module — a computed queue of compliance issues and upcoming deadlines for the active company

No mail/mailroom feature — skip that entirely.

---

## 1. Frontend

### Placement
Insert the new hero markup **above** the existing `.zentra-header` block inside `.zentra-dashboard`, in `dashboard.html`. Do not remove or restructure the existing filter header — it stays as-is below the hero.

### Design system
Reuse the existing Zentra tokens already defined in `dashboard.html` (`--zentra-card-bg`, `--zentra-border`, `--zentra-radius`, `--zentra-shadow`, `--text-dark`, `--text-muted`, `--accent-blue`). Add a new gradient background token for the hero only (soft warm gradient, similar tone to the rest of the UI — do not hardcode a clashing palette).

### Structure

**Greeting bar**
- `H1`: time-based greeting + first name — e.g. "Morning, {{ current_user.first_name }} 👋"
  - Morning: before 12:00
  - Afternoon: 12:00–17:00
  - Evening: after 17:00
- Subtitle: "Take a look into {{ active_company.name }}"
- Right-aligned button: "Entity Profile" → links to the entity/company detail route (create if it doesn't exist — see backend section)

**Important Actions**
- Section header: "Important Actions ({{ actions|length }})"
- If `actions` is empty: show an empty state, e.g. "You're all caught up ✅" — do not hide the section entirely
- Otherwise render each action as a row/card with:
  - Icon (flag for issues, calendar/clock for deadlines)
  - Title (e.g. "Solve issue with: EIN Order")
  - Relative time (e.g. "2 days ago" for issues, "due in 15 days" for deadlines)
  - Chevron (`>`) that routes to the actual resolution flow for that specific action — not a generic page
- Sort order: critical/red issues first, then deadlines, soonest due date first

### States/behavior
- Each action row should support a "dismiss/snooze" control (icon button) that hides it from the queue without deleting the underlying record — snoozed actions reappear after their snooze window or when re-triggered by new data.
- Action count badge is always live — recompute on page load, not cached/static.

---

## 2. Backend

### Data model
Add (or reuse if equivalent already exists):

**`dashboard_actions`** (or derive dynamically — see "computed vs stored" below)
| field | type | notes |
|---|---|---|
| id | PK | |
| company_id | FK → companies | scopes to `active_company` |
| type | enum: `issue`, `deadline` | drives icon + sort priority |
| title | string | e.g. "Solve issue with: EIN Order" |
| source | string | what subsystem raised this (e.g. `ein_order`, `annual_report`) |
| source_id | FK/int | id of the underlying record this action points to |
| severity | enum: `critical`, `normal` | critical issues always sort first |
| due_at | datetime, nullable | used for deadline countdown; null for issues |
| created_at | datetime | used for "X days ago" on issues |
| snoozed_until | datetime, nullable | if set and in the future, exclude from active queue |
| resolved_at | datetime, nullable | if set, exclude from active queue |

### Computed vs. stored
Two valid approaches — pick based on how many "action sources" you already have:
- **Computed on request**: a service function queries each subsystem (EIN orders, compliance filings, annual report deadlines, etc.) directly and assembles the list at page-render time. Simpler if there are only 2–3 sources today.
- **Stored + synced**: a background job/webhook writes rows into `dashboard_actions` whenever a subsystem generates or resolves an actionable item. Better once there are more than a few sources, since the dashboard query stays cheap (`SELECT ... WHERE company_id = ? AND resolved_at IS NULL AND snoozed_until IS NULL OR snoozed_until < now()`).

Start with computed-on-request; migrate to stored+synced if the number of sources grows.

### Routes/endpoints needed
- `GET /entity-profile` (or `/companies/<id>`) — Entity Profile page (status, formation date, registered agent, EIN, etc.) if it doesn't already exist
- `POST /actions/<id>/dismiss` — snooze an action (sets `snoozed_until`)
- Existing per-source resolution routes should be linked to from each action's chevron (e.g. EIN issue → EIN order detail/fix page; Annual Report deadline → filing flow)

### Query for the hero
```
actions = get_important_actions(company_id=active_company.id)
# returns list sorted: severity=critical first, then by due_at ascending / created_at descending
```
Pass `actions` into the `dashboard.html` template context alongside the existing `active_company`, `date_from`, `date_to`, etc.

### Backend logic for relative time
- Issues: `created_at` → "X days ago"
- Deadlines: `due_at` → "due in X days" (or "due today" / "overdue by X days" if past due — style overdue ones as critical automatically)

---

## 3. Acceptance criteria
- [ ] Hero renders above the existing filter header without breaking current layout/spacing
- [ ] Greeting updates correctly by time of day and shows correct user/company name
- [ ] Entity Profile button links to a working page
- [ ] Important Actions count badge matches the number of rows rendered
- [ ] Empty state shows when there are zero active actions
- [ ] Each action's chevron routes to the correct resolution flow for its `source`
- [ ] Dismiss/snooze hides the action and it does not reappear until snooze window passes
- [ ] Overdue deadlines automatically render as critical/red
- [ ] No mailroom-related code, tables, or routes added
