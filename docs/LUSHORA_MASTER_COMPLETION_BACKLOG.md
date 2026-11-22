# LUSHORA Master Completion Backlog
Branch: `lushora-premium-v2`
Audit basis: repository source inspection (README, backend API routes/models, frontend portal and tests). Statuses are code-presence estimates; only features validated end-to-end are marked verified.

## Completion rule
Mark a task DONE only after implementation, automated tests, frontend production build, and functional/regression validation. External credentials, local-device/browser access, or real-world integrations must be explicitly marked BLOCKED/NEEDS USER TEST if unavailable.

## Phase 0 — Existing foundation audit (IN PROGRESS)
- [ ] Validate current marketplace/customer/provider/admin flows end-to-end
- [ ] Audit current tests for meaningful assertions and coverage gaps
- [ ] Check existing UI consistency, responsiveness, accessibility, loading/error/empty states
- [ ] Audit database migration, backups, sensitive upload handling and security
- [x] Establish repository master backlog (feature/test matrix still needs detailed validation)

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
- [ ] Staff-specific availability
- [ ] Break/holiday/closure integration
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
- [ ] Advance/full payment options
- [ ] Payment status lifecycle and idempotency
- [ ] Failed/pending payment recovery
- [x] Refund request/review workflow foundation (manual; gateway refund execution and partial-refund accounting remain pending)
- [ ] Platform commission rules
- [ ] Provider payout calculation and payout operations
- [ ] Transaction ledger and reconciliation
- [ ] Customer receipt/invoice
- [ ] Admin finance dashboard and audit trail
- [ ] Payment tests (sandbox; live credentials need user setup)

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
