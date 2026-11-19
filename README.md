# LUSHORA — Premium Beauty & Wellness Marketplace

LUSHORA is a premium beauty and wellness marketplace MVP for discovery, booking requests, customer accounts, provider onboarding and admin review.

## Current implemented foundation
- Premium responsive editorial homepage and category discovery
- Provider discovery by category/city/locality, verified filter and price filters at API level
- Guest booking requests with provider/service validation and overlap checks
- Customer/provider registration and login APIs with PBKDF2 password hashing and signed bearer tokens
- Customer profile endpoint and customer booking history
- Provider business onboarding with pending approval
- Admin provider approval/rejection endpoints
- Provider service management API and provider booking dashboard APIs
- Booking lifecycle API: confirm, reject, cancel and complete, with role/ownership checks
- Admin overview and booking list APIs (admin-only)
- SQLite schema migration helper for the new ownership fields
- GitHub Actions workflow for backend tests and frontend production build

## Run locally on Windows
1. Install Python 3.12 or 3.13 and Node.js LTS.
2. Run `RUN_LUSHORA.bat`.
3. Open http://127.0.0.1:5173.
4. Use **Load sample listings** to add demo providers.
5. API docs: http://127.0.0.1:8000/docs.

## Admin bootstrap
Set these environment variables before starting the backend to create the first admin user on startup:
- `LUSHORA_ADMIN_EMAIL`
- `LUSHORA_ADMIN_PASSWORD` (minimum 12 characters)
- Optional `LUSHORA_ADMIN_NAME`
- `LUSHORA_AUTH_SECRET` (set a long random secret; default is development-only)

The admin is created only if the configured email does not already exist. Do not use the development defaults in production.

## Current limitations / remaining work
- OTP/phone verification is not implemented.
- Live availability, business hours, breaks, holidays and slot locking are not yet implemented.
- Payment gateway, refunds, commissions and provider payouts are not implemented.
- Reviews and review moderation are not implemented.
- Email/SMS/WhatsApp notifications are not implemented.
- Admin and provider UI is an MVP dashboard; more operational controls and polish remain.
- Deployment, production database migrations, rate limiting, monitoring, backup/restore, privacy/security audit and end-to-end testing remain.
- Demo provider ratings/verification are sample values, not real endorsements.

## Tech stack
- Frontend: React 19 + Vite
- Backend: FastAPI + SQLAlchemy
- Database: SQLite local MVP; production database configuration via `LUSHORA_DATABASE_URL`

## Testing
The repository includes backend tests and CI workflow for backend pytest and frontend `npm run build`. Tests/build must be confirmed through a successful CI run or local execution before declaring them passed.

This project is an MVP development build and is **not production-ready**.
