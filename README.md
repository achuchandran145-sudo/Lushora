# LUSHORA — Premium Beauty & Wellness Marketplace

**LUSHORA** is a premium local beauty and wellness discovery and booking marketplace MVP. It connects customers with beauty businesses, lets customers request appointments, gives businesses tools to manage profiles/services/bookings, and provides Admin review and reporting.

> **Status:** Active MVP development — not production-ready.

## Product idea
- Customer discovers beauty services and local providers, then requests a booking.
- Businesses register, submit their profile for Admin review, manage services and booking requests, and track activity.
- Admin reviews/approves business registrations and monitors customer/business accounts and activity.

Initial categories: **Makeup, Salon, Skin Clinic, Nail Studio**. Initial target cities: **Chennai, Coimbatore and Tiruvannamalai**.

## Features implemented

### Marketplace/customer foundation
- Responsive premium LUSHORA homepage and multi-category discovery (Makeup, Salon, Skin Clinic, Nail Studio).
- Homepage footer Admin Login link; Admin entry is removed from Customer Login.
- Provider discovery by category/city/locality.
- API-level filters for verified and price.
- Customer phone OTP login; after verification, first-time customers complete first name, last name, street address, city and locality profile setup.
- Customer profile/address storage and profile API; city/locality selection supports initial launch cities.
- Customer registration/login APIs, profile and booking-history endpoints.
- Guest booking request flow with provider/service validation and appointment-overlap checks.

### Business/provider
- Business onboarding and pending Admin approval.
- Service management APIs.
- Provider booking dashboard and booking lifecycle actions (confirm, reject, cancel, complete).
- **Recent dashboard implementation:** daily/hourly booking activity chart, monthly booking trends, revenue KPI and completed-booking revenue trend, new vs repeat client insights, client directory, booking search/filters, pagination, and native Excel (.xlsx) export.
- Recent dashboard features are committed but **still require local testing** with sample data.

### Admin
- Admin login/dashboard.
- Business verification queue and approve/reject workflow.
- Approved business directory and Admin overview/booking list.
- **Customers & Users report:** totals for customer and business accounts, date range, account-type filters, search by name/phone/email, user listing and native Excel export.
- Customer residential addresses are not yet collected/stored in the current profile schema; address collection/display/export is pending.
- Recent reporting features **still require local testing**.

### Business verification workflow updates
- Admin review supports **Approve**, **Under review**, **Return to Pending**, **Reject**, and **Delete permanently**.
- Return to Pending maps to the `submitted` queue status; it does not delete the application.
- Permanent delete removes the verification record, uploaded files (when safely within the private storage root), and matching provider listings/services.
- Verification documents are stored in a private folder structure: business name / city / locality / account + verification ID. Files remain accessible only through authenticated Admin document endpoints.
- Production deployments must configure `LUSHORA_VERIFICATION_UPLOAD_DIR` to a persistent private volume. Local/private filesystem storage is not a secure production document vault.

### Deployment connectivity
- Frontend builds need `VITE_LUSHORA_API` set to the deployed backend API base (including `/api`).
- Backend must set `LUSHORA_CORS_ORIGINS` to the exact deployed frontend origin(s), comma-separated. Localhost development origins are retained by default.
- A browser **Failed to fetch** error can still occur if the API URL is missing/wrong, backend is unavailable, or the deployed frontend origin is not in the backend CORS allow-list.

## Production foundation/security gates

Production startup is intentionally fail-closed. Production must use PostgreSQL with Alembic migrations, a strong `LUSHORA_AUTH_SECRET`, development OTP disabled, exact HTTPS CORS origins, a private absolute verification-document storage directory outside the repository, and a private absolute backup directory with at least 7-day retention configured.

### Production migration

From `backend`, set `LUSHORA_DATABASE_URL` to a PostgreSQL URL using the installed psycopg driver, then run:

```bash
./scripts/migrate_production.sh
```

The API will refuse to start in production until the Alembic version table exists and contains an applied revision. Do not run the API before migrations.

### Backup and restore verification

```bash
./scripts/backup_postgres.sh
```

For restore verification, use a disposable PostgreSQL database only:

```bash
LUSHORA_RESTORE_DATABASE_URL='postgresql+psycopg://...' BACKUP_FILE='/private/backup/lushora-YYYYMMDDTHHMMSSZ.dump' ./scripts/restore_verify_postgres.sh
```

Backups must be scheduled by the deployment platform and tested periodically. These scripts do not create a schedule or prove that a cloud backup destination is configured. Production infrastructure, real backup/restore drills, SMS provider, and penetration testing remain external verification requirements.

## Tech stack
| Component | Stack |
|---|---|
| Frontend | React 19, Vite |
| Backend | FastAPI, Uvicorn |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Local database | SQLite |
| Excel reporting | openpyxl |
| Tests | pytest |
| Python | **3.13 recommended** (3.12 also supported per current setup) |
| Node | Node.js LTS + npm |
| OS instructions | Windows / PowerShell |

## Setup & run (Windows)

### Requirements
Install Python 3.13, Node.js LTS/npm and Git.

### Recommended startup
From the project root:
```powershell
.\RUN_LUSHORA.bat
```

### Manual backend setup (Python 3.13)
```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Manual frontend setup
```powershell
cd frontend
npm install
npm run dev
```

### Local URLs
| Portal | URL |
|---|---|
| Homepage | http://localhost:5173 |
| Customer login | http://localhost:5173/customer/login |
| Business login | http://localhost:5173/business/login |
| Business onboarding | http://localhost:5173/business/onboarding |
| Admin login | http://localhost:5173/admin/login |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

## Admin account setup
Run the setup helper from the repository root:
```powershell
.\scripts\setup-admin.ps1
```
It prompts for the password securely (input is hidden) and requires a password of at least 12 characters. Setup helper's configured email is:
```
admin@lushora.local
```
Never commit passwords, tokens, or production secrets.

### Admin account recovery

- Admin sign-in provides **Forgot your password?** and **Forgot your Admin email?** links.
- Password reset uses one-use, 30-minute links. Only an HMAC digest of the token is stored; completing a reset revokes all existing Admin sessions.
- Admin email reminders are sent only to the separately configured recovery mailbox. Protect that mailbox with MFA.
- Configure these backend environment variables; never commit their values:
  - `LUSHORA_ADMIN_RECOVERY_EMAIL` — owner-controlled recovery inbox.
  - `LUSHORA_ADMIN_RECOVERY_BASE_URL` — public frontend base URL, without a trailing slash (falls back to `LUSHORA_FRONTEND_URL`).
  - `LUSHORA_SMTP_HOST`, `LUSHORA_SMTP_PORT` (587 with STARTTLS or 465 with implicit TLS), `LUSHORA_SMTP_USERNAME`, `LUSHORA_SMTP_PASSWORD`, `LUSHORA_SMTP_FROM`.
  - Optional `LUSHORA_SMTP_TIMEOUT_SECONDS` (default 10).
- Apply the Alembic migration before deploying: `python -m alembic -c alembic.ini upgrade head`.
- Until SMTP and the recovery inbox are configured, the API deliberately sends no recovery email. Requests return generic responses and do not expose whether an account exists.



## Git workflow
- Active working branch: **lushora-premium-v2**.
- Pull before work:
```powershell
git pull origin lushora-premium-v2
``
- Code changes stay on this branch unless the owner explicitly approves another branch.
- Do not switch branches or merge without explicit approval.

## Next roadmap
### Immediate
- [ ] Test the latest Business Dashboard charts, revenue, filters, client insights, pagination and Excel export locally.
- [ ] Test Admin customer/business report, filters and Excel export locally.
- [ ] Seed realistic sample users, providers and bookings for testing.
- [ ] Fix bugs identified during testing.
- [ ] Expand and maintain city/locality database; allow customer profile editing and show address in Admin/report (with privacy/security controls).

### Planned product work
- [ ] Customer OTP/mobile verification.
- [ ] Live availability, business hours, breaks, holidays and slot locking.
- [ ] Payment gateway, refunds, commissions and provider payouts.
- [ ] Reviews, ratings and moderation.
- [ ] Email/SMS/WhatsApp notifications.
- [ ] Admin controls for subscriptions, Top 10 placements and operational settings.
- [ ] Production-safe verification-document storage.
- [ ] Deployment, production database migrations, monitoring, backups/restore.
- [ ] Rate limiting, privacy/security audit and end-to-end tests.

## Testing
Backend tests and a CI workflow are included for pytest and frontend production build. Check actual local/CI results before declaring them successful. Recent dashboard/report work is implemented in the branch but not yet verified on the user's machine.

## Production warning
This is a development MVP, **not production-ready**. Do not use real sensitive identity documents in local testing. Authentication secrets, customer personal data, document storage, deployment, database, payments, notifications and operational monitoring require production hardening.

## Status at a glance
**Implemented:** marketplace foundation, customer/business accounts, provider onboarding and Admin approval, booking lifecycle, Business analytics/reporting, Admin customer/business account analytics and Excel export.

**Validating next:** test recent dashboards and exports with sample data, then fix issues.

**Next major build:** customer profile/address management, followed by booking availability, notifications, payments and production hardening.


## Notification channel framework
- User preferences API: GET/PUT `/api/me/notification-preferences`
- Admin readiness API: GET `/api/admin/notification-channels`
- Admin delivery log API: GET `/api/admin/notification-deliveries`
- FCM env vars: `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`
- WhatsApp Cloud API: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`
- SMS placeholder: `SMS_PROVIDER_API_KEY`, `SMS_SENDER_ID`

This framework tracks channel readiness and creates delivery-log records. It does not yet dispatch external messages. Provider adapters, worker, retries, and delivery receipts remain to be implemented. Credentials are not stored in Git.


### Firebase Web Push setup (optional)
To enable customer browser push notifications, configure the frontend environment:
- `VITE_FIREBASE_WEB_CONFIG`: Firebase web app config JSON (public client config)
- `VITE_FIREBASE_VAPID_KEY`: Firebase Cloud Messaging Web Push public VAPID key

Customers sign in, opt in under Notification Preferences, and grant browser permission. LUSHORA registers the FCM token with the backend. Turning Push off disables the preference and deactivates the browser token. Browser push requires HTTPS (localhost is allowed for development).

## External notification delivery (backend framework)

The notification worker is a separate process and must run alongside the API:

```powershell
cd backend
.venv\Scripts\activate
python -m app.notification_worker
```

Configure channel credentials in the environment (never commit secrets):

- **Push (Firebase Admin):** `FCM_SERVICE_ACCOUNT_JSON` — JSON content of a Firebase service account. Client-side Firebase token generation and registration UI still need to be connected.
- **WhatsApp Cloud API:** `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` — requires Meta setup and approved template handling for applicable outbound messages.
- **SMS (Twilio):** `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM` — configure an approved sender/number with Twilio.
- Optional worker settings: `NOTIFICATION_WORKER_POLL_SECONDS` (default 10), `NOTIFICATION_MAX_ATTEMPTS` (default 5).

The worker processes queued deliveries, logs attempts and provider IDs, and retries failures with exponential backoff. It does not run automatically inside the FastAPI server. Push delivery is not end-to-end until the frontend registers device tokens. WhatsApp template compliance, channel opt-in/consent UX, provider account setup and production testing are still required before launch.
