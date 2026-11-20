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
- Responsive premium LUSHORA homepage and category discovery.
- Provider discovery by category/city/locality.
- API-level filters for verified and price.
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
- [ ] Add customer address collection/profile editing and show addresses in Admin/report (with privacy/security controls).

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
