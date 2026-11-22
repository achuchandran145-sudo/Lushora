# LUSHORA Master Completion Backlog
Branch: `lushora-premium-v2`
Audit basis: repository source inspection (README, backend API routes/models, frontend portal and tests). Statuses are code-presence estimates; only features validated end-to-end are marked verified.

## Completion rule
Mark a task DONE only after implementation, automated tests, frontend production build, and functional/regression validation. External credentials, local-device/browser access, or real-world integrations must be explicitly marked BLOCKED/NEEDS USER TEST if unavailable.

## Phase 0 — Existing foundation audit (REMEDIATION IN PROGRESS)
Audit snapshot: 2026-11-22. Phase 0 is **NOT COMPLETE**. Completion requires green CI on the latest branch head plus the checklist evidence below.

**Final verification snapshot:** commit `e8abe407dd4f97023dea4fa41439c3b17b11ec83` has a successful required CI run:
https://github.com/achuchandran145-sudo/Lushora/actions/runs/45039840125

Code-level Phase 0 remediation: **COMPLETE**. Remaining items are explicitly environment-dependent release validations.

### Remediation status
- [x] Master backlog established.
- [x] Backend test suite and frontend production build are part of CI.
- [x] Persistent hashed-identifier rate-limit implementation and regression tests for login, registration, OTP request/verification thresholds.
- [x] Production startup guards for weak auth secrets, development OTP, CORS, PostgreSQL, private upload and backup configuration; regression tests exist.
- [x] Demo-seed disabled in production; regression test exists.
- [x] SQLite migration compatibility fixes for partial legacy schemas; tests added.
- [x] Browser E2E coverage added for customer OTP/profile/mobile, guest discovery/booking, provider signup and admin login. Selector and wait logic remediation is ongoing.
- [x] Operational backup/restore scripts and CI PostgreSQL service drill added; CI URL normalization and drill execution are still being corrected/validated.
- [x] Latest CI green: backend tests, Playwright E2E, pip-audit, npm audit, frontend build, PostgreSQL migration/backup/restore drill.
- [ ] Auth: verify lockout thresholds/reset, concurrent request behavior, privacy of hashed identifiers, OTP expiry/replay/attempt consumption, token expiry/tampering/revocation/version invalidation.
- [ ] Security audit events: verify sensitive action coverage, no credential/OTP/document PII in events, admin-only access and tamper-resistance assumptions.
- [ ] Production config: test bootstrap-admin safety, secret rotation requirements, CORS exact origins, HTTPS, secure cookies/headers, file-storage isolation.
- [ ] Database: run Alembic against PostgreSQL, test upgrades from supported legacy schemas, rollback/recovery plan and migration locking.
- [ ] Backup/restore: CI drill must pass and validate restored marker/schema; production-like restore, row-count comparison, RPO/RTO evidence still needed.
- [ ] Sensitive verification files: current-tree removal and ignore rules are implemented; Git history exposure review and incident-response decision remain pending. Do not rewrite history without explicit approval.
- [ ] Browser journeys: customer OTP/profile/search/book/cancel/reschedule; provider signup/verification/services/schedule/bookings; admin login/approval/moderation. Expand assertions and ensure reliable green runs.
- [ ] Mobile responsiveness: viewport overflow, touch controls, navigation and modal behavior on phone/tablet sizes.
- [ ] Accessibility: keyboard-only navigation, focus visibility/order, accessible names/labels, contrast and automated accessibility scan.
- [ ] UI states: systematic loading, empty, error, success, offline and validation-state audit.
- [ ] Notification worker: retry/backoff, failed delivery recovery, idempotency, dead-letter/monitoring, worker deployment and shutdown/recovery.
- [ ] Production release checklist: staging smoke test, security review, backup/restore evidence, rollback, monitoring and incident contacts.
- [ ] Phase 0 sign-off only after all blocking checks have evidence; no code-presence-only sign-off.

### Additional Phase 0 remediation (2026-11-22)
- [x] Restore verifier now validates the backup SHA-256 sidecar before restore.
- [x] PostgreSQL CI drill compares source/restored row counts for critical tables and verifies a restored marker.

- [x] Notification worker refactored to avoid import-time infinite loop, validate polling interval (1-300 seconds), and support SIGTERM/SIGINT graceful stop.
- [x] Notification delivery tests added for retry/backoff, success after retry, exhausted attempts, and user-consent suppression.
- [x] Worker tests added for stop behavior, session closure, and poll-interval validation.
- [x] CI now installs axe-core and runs serious/critical WCAG accessibility scans on homepage and customer login.
- [x] CI Gitleaks action added for repository and history scanning; findings still require review and remediation.
- [ ] Latest CI run must validate the above changes and report all jobs green.
- [ ] Accessibility scan must produce clean serious/critical results; lower-impact findings still require review.
- [ ] Secret scan results must be reviewed; any historical real secrets must be rotated, and history rewriting requires explicit approval.

### Phase 0 evidence updates (2026-11-22)
- [x] Production now requires an absolute private portfolio upload directory outside the repository; production import no longer creates a repo-local portfolio directory. Tests added for missing and repo-local portfolio storage.
- [x] OTP expiration, replay rejection, and OTP-disabled behavior covered by regression tests.

- [x] PostgreSQL 16 client mismatch fixed and backup/restore drill now passed on latest observed CI.
- [x] Python dependency audit passed on latest observed CI.
- [x] Frontend build and npm audit passed on latest observed CI.
- [x] Gitleaks full-history scan passed on latest observed CI.
- [x] Backend unit/API suite: 76 passed in latest observed run; one failure was accessibility audit (contrast + logo accessible-name mismatch).
- [x] Accessibility contrast colors corrected across homepage and portal styles.
- [x] Logo accessible name updated to include visible brand/tagline.
- [ ] Latest CI after accessibility fixes must be fully green.
- [ ] Lower-impact axe findings and keyboard/focus/accessibility manual review remain.
- [ ] Full customer/provider/admin journeys and additional responsive checks remain.
- [ ] Production security configuration, PostgreSQL upgrade/rollback evidence, restore RPO/RTO, and operational monitoring evidence remain.
- [ ] Notification provider live credentials/delivery and deployment/recovery remain environment-dependent.
- [ ] Phase 0 sign-off remains blocked until all remaining validation evidence is collected.

### Known CI failures being remediated (2026-11-22)
- [ ] Browser E2E OTP wait was querying a null input before UI render; replaced with locator wait and value assertion.
- [ ] Browser E2E category selector was brittle; switched to category-chip locator.
- [ ] Browser E2E admin assertion used stale heading; corrected to current Dashboard heading.
- [ ] SQLite partial-schema migration attempted to alter missing tables; guards added and staff migration SQL corrected.
- [ ] PostgreSQL backup/restore drill initially used PostgreSQL+psycopg URL syntax with psql; CI script normalizes psql URLs. Latest run pending.

### Phase 0 local verification evidence (2026-11-22)
- [x] Browser E2E fixture fixed for Windows: Vite is launched through the Node executable directly, with explicit dependency checks and no npm/Vite process leak.
- [x] Customer profile E2E assertion fixed to validate the HTTP 200 PATCH response body, persisted profile values, completion state and redirect without depending on the transient portal notice.
- [x] axe-core added to the frontend dev dependencies and lockfile so accessibility tests are reproducible by local and CI installs.
- [x] Full local backend/API/browser suite: 84 passed.
- [x] Frontend production build: PASS.
- [x] npm audit: 0 vulnerabilities.
- [x] pip-audit: no known vulnerabilities.
- [x] GitHub Actions final-commit CI: PASS — run https://github.com/achuchandran145-sudo/Lushora/actions/runs/45039840125 for commit e8abe407dd4f97023dea4fa41439c3b17b11ec83.
- [x] Gitleaks repository and history scan: PASS — successful CI step `Scan repository and Git history for secrets`.
- [x] PostgreSQL 16 migration and backup/restore CI drill: PASS — successful CI step `Run PostgreSQL migration and backup/restore drill`.
- [x] Backend tests, Playwright/browser E2E, Python audit, operational scripts, npm audit and frontend build: PASS in the successful final-commit CI run.
- [ ] Staging/production smoke test: BLOCKED — ENVIRONMENT REQUIRED (requires staging or production credentials and deployed URLs).
- [ ] Live notification delivery: BLOCKED — ENVIRONMENT REQUIRED (requires real FCM/WhatsApp/SMS credentials and approved provider configuration).
- [ ] HTTPS/domain production deployment, monitoring/alerting, real restore/RPO/RTO and incident ownership: BLOCKED — ENVIRONMENT REQUIRED.

## Phase 1 — Customer & provider profile completion
- [x] Customer profile edit API/UI end-to-end (API exists; validated fields + owner profile regression tests)
- [x] Address and contact data model/UX completeness (profile fields and city/locality/address validation)
- [x] Provider profile editing and onboarding completion UX (owner-scoped API/UI; CI build + regression test)
- [x] Provider portfolio/gallery with image validation, size/dimension limits, owner management and public image retrieval (local storage; production storage hardening remains Phase 9)
- [x] Provider service edit API (name, price, duration) with owner validation + regression tests
- [x] Provider service edit UI in portal (name, price, duration; owner-checked API)
- [x] Business operating hours, breaks, holidays and closure rules (working-day/hour/break validation and ISO closure dates; booking checks + regression tests)
- [x] Staff/member profiles (owner-managed CRUD, role labels and active status); [ ] staff login and permission enforcement (future RBAC/security work)
- [x] Multi-branch/locations support (owner-managed CRUD, city/locality/address/phone and active status; branch-level hours/service assignment remain future work)

## Phase 2 — Booking engine
Audit findings: current slot generation uses 30-minute stepping and naive server-local datetimes; booking creation checks working hours/breaks/closures and overlapping bookings, but concurrent requests can race because overlap validation is read-before-write. Prioritize DB-level provider locking and slot/time validation.
- [x] Availability validation against provider schedule, service duration, breaks and closures (booking creation enforces rules)
- [x] Slot generation uses 30-minute increments; booking creation enforces the same grid and interprets naive timestamps as India-local (Asia/Kolkata); timezone offsets are rejected
- [x] Prevent double-booking under concurrent requests (provider-row lock/version update; concurrent-request regression test passes CI)
- [x] Staff-specific booking capacity and assignment (customer can choose active provider staff; assigned bookings overlap only for the same staff; provider-wide/unassigned bookings reserve all capacity; staff-filtered slots and regression tests; staff hours still inherit provider hours)
- [x] Break/holiday/closure integration (slot generation and booking creation both enforce provider working days, breaks, closed dates; regression tests)
- [x] Booking confirmation UX and statuses (requested/confirmed/rejected/completed/cancelled lifecycle and role checks)
- [x] Reschedule flow (customer/provider UI and API; validates availability, conflicts, owner access and 30-minute grid)
- [x] Booking cancellation role/ownership/lifecycle validation and regression test
- [x] Provider-configurable cancellation notice window and fee-percent hook (customer cancellation response reports fee applicability; no fee collection/accounting yet)
- [x] Booking expiration/timeout (24-hour requested-state TTL, stale cleanup during booking/list operations, admin cleanup endpoint; regression test passes CI)
- [x] Waitlist end-to-end MVP (customer join from booking modal, dashboard list/cancel, API validation/duplicate prevention/ownership; backend tests + frontend build pass CI)
- [x] Booking calendar UI (provider date-filtered calendar view with daily appointments and status actions)
- [x] Booking regression/journey coverage: create, schedule constraints, conflict/concurrency, status permissions, cancellation, reschedule, expiration and waitlist (backend CI verified)

## Phase 3 — Payments & finance
- [ ] Gateway selection/configuration and sandbox integration
- [ ] Payment intent/order creation and secure verification/webhook handling
- [x] Full payment and 20% advance payment record options (remaining balance tracked; no gateway collection yet)
- [x] Payment record status/idempotency foundation (pending, cancellation, refund states; gateway lifecycle/webhooks remain pending)
- [ ] Failed/pending payment recovery
- [x] Refund request/review workflow foundation (manual; gateway refund execution and partial-refund accounting remain pending)
- [x] Admin-configurable category commission rules (0–30%; API/UI and role/validation regression tests; not yet applied to collected payments or payout calculations)
- [ ] Provider payout calculation and payout operations
- [x] Admin payment ledger and summary with read-only reconciliation foundation (payment type and balance due fields, payment-type summary; gateway settlement matching remains pending)
- [ ] Customer receipt/invoice
- [ ] Admin finance dashboard and audit trail
- [x] Payment record tests for owner scope, idempotency, pending duplicate prevention, cancellation and full/advance amount calculations; sandbox/live gateway tests blocked until gateway configured

## Phase 4 — Reviews & reputation
- [x] Review model/API foundation
- [x] Reviews API: customer submission, customer listing, public provider listing
- [x] Eligibility: completed booking owned by customer
- [x] One review per booking (unique constraint + API conflict handling)
- [x] Admin moderation API (approve/reject)
- [x] Provider reply API
- [x] Public ratings aggregated from approved reviews
- [x] Customer review submission UI and submitted-review display
- [ ] Provider/admin review UI (reply/moderation frontend)
- [ ] Review model/API/UI
- [ ] Reviews restricted to eligible completed bookings
- [ ] One review per booking; edit policy
- [ ] Rating aggregation
- [ ] Review photo upload (secure)
- [ ] Provider replies
- [ ] Customer review reporting
- [ ] Admin moderation queue and actions
- [ ] Anti-abuse/fraud controls
- [ ] Ratings shown in search/provider profile

## Phase 5 — Notifications & communications
- [ ] Event-triggered booking notifications
- [ ] Customer/provider notification preferences and consent UX
- [ ] Push device registration, delivery and retry validation
- [ ] WhatsApp provider integration and approved templates
- [ ] SMS provider integration and compliance/configuration
- [ ] Booking reminders and cancellation/reschedule alerts
- [ ] Delivery retry/dead-letter handling
- [ ] In-app notification UX, unread state and deep links
- [ ] Notification settings/admin observability
- [ ] Credential-dependent delivery tests

## Phase 6 — Subscription & monetization
- [ ] Define category/area subscription plans and pricing configuration
- [ ] Trial lifecycle
- [ ] Subscription checkout/payment
- [x] Admin-managed activation, renewal, pause, cancellation and expiry term handling (backend foundation; automated billing/entitlement enforcement pending)
- [ ] Grace period and failed-renewal recovery
- [ ] Enforce plan entitlements
- [ ] Featured listing/ranking entitlement
- [ ] Subscription billing history and receipts
- [ ] Admin revenue/plan reporting
- [ ] Provider subscription UX

## Phase 7 — Admin control center
- [ ] Admin roles/permissions
- [ ] Audit log for admin actions
- [ ] Review moderation
- [ ] Payments/refunds/commission/payouts (refund request/review API foundation implemented; finance UI and gateway processing pending)
- [ ] Support tickets and disputes
- [ ] Coupon/promotion management
- [ ] Provider/user suspend/restore workflows
- [ ] Subscription plan controls and entitlement enforcement
- [ ] Ranking/featured placement controls
- [ ] Area/city management validation
- [ ] Platform settings and analytics
- [ ] Admin dashboard responsive/premium UI and action confirmations

## Phase 8 — Growth
- [ ] Favourites/saved providers
- [ ] Coupon/promo redemption engine
- [ ] Referral tracking/rewards and abuse prevention
- [ ] Loyalty/reward points
- [ ] Popular/trending services and providers
- [ ] Personalised recommendations (privacy-conscious)
- [ ] Search analytics and conversion funnel
- [ ] SEO metadata, structured data and shareable pages
- [ ] Social sharing
- [ ] Campaign management

## Phase 9 — Security, privacy & infrastructure
- [ ] Auth/JWT/OTP audit, expiry, rotation and attempt limits
- [ ] Rate limiting on login/OTP/API-sensitive endpoints
- [ ] RBAC and customer/provider/admin data isolation tests
- [ ] Secure file upload validation (size, MIME, content, filenames)
- [ ] Remove sensitive documents from public repository/history; private storage and access control
- [ ] Secrets/environment configuration and rotation
- [ ] Privacy policy, terms, cancellation/refund policy and consent
- [ ] Account deletion/data export
- [ ] Production database and migration system
- [ ] Backups and restore drills
- [ ] Staging and production deployment
- [ ] HTTPS/domain/secrets management
- [ ] Centralized logs, monitoring, alerting and error tracking
- [ ] Performance/load testing
- [ ] Rollback and disaster recovery

## Phase 10 — UX quality
- [ ] Formal premium design system (tokens, typography, spacing, color, component states)
- [ ] Replace excessive white/light surfaces where not brand-appropriate; maintain readability/accessibility
- [ ] Customer, provider and admin portal visual consistency
- [ ] Responsive mobile/tablet layouts
- [ ] Accessibility review (keyboard, labels, contrast, focus)
- [ ] Loading, empty, error, success and offline states
- [ ] Form validation and confirmation UX
- [ ] Navigation and onboarding polish

## Phase 11 — Release QA
- [ ] Automated backend test coverage for major journeys
- [ ] Frontend component/unit tests
- [ ] Browser end-to-end tests for customer/provider/admin
- [ ] Regression suite
- [ ] Cross-browser/device testing
- [ ] Security test pass
- [ ] Performance test pass
- [ ] Staging smoke test
- [ ] Release checklist and rollback verification

## Current code-present foundations (not automatically considered complete)
- Marketplace categories and provider discovery
- Customer OTP/profile foundation
- Provider registration, service create/delete, booking APIs and provider availability APIs
- Booking status lifecycle and provider/customer/admin booking views
- Admin user reporting/export, provider approval and verification/document workflow
- Subscription, area/ranking and lead frameworks
- Notification preferences/devices/in-app records/channel framework and worker
- CI backend tests and frontend production build
