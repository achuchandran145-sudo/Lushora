# LUSHORA — Premium Marketplace UI Upgrade

This is an upgraded **prototype** of the LUSHORA beauty and wellness marketplace. It builds on the supplied starter project and keeps its FastAPI + SQLite backend.

## Run on Windows
1. Install Python 3.11+ and Node.js 20+ (LTS), plus Git if cloning.
2. Extract the project.
3. Double-click `RUN_LUSHORA.bat`.
4. Open http://127.0.0.1:5173 if the browser does not open automatically.
5. Use **Load demo listings** to populate sample providers.

API documentation: http://127.0.0.1:8000/docs

## What's improved
- Redesigned responsive customer discovery experience with a premium editorial visual system.
- Category tiles for Makeup, Salon, Skin Clinic and Nail Studio.
- Search, city filter, category filter, verified-only filter and sorting.
- Provider cards, provider detail modal and service selection.
- Appointment request form with client-side validation and request submission to the API.
- My Bookings page showing requests retrieved from the backend.
- For Business page with backend summary metrics and clear prototype limitations.
- Existing demo seeding and API health endpoints retained.

## Existing backend capabilities
- Provider and service tables in SQLite.
- Provider listing and detail endpoints.
- Category/city/locality/price/verified filtering on the API.
- Booking request creation with provider/service validation and future-date validation.
- Booking list endpoint and admin summary endpoint.
- Demo data seed endpoint.

## Important limitations — not production-ready
This package is **not** a complete production marketplace. It does not yet include:
- Customer/provider/admin authentication, authorization or account management.
- Provider self-registration, provider dashboard or admin management workflows.
- Real provider availability calendars, slot holds, conflict prevention or booking confirmation workflow.
- Payments, refunds, commissions, payouts or payment webhook verification.
- WhatsApp/SMS/email notifications.
- Real provider photos, portfolio uploads, reviews or moderation.
- PostgreSQL deployment, migrations, backups, monitoring, rate limiting or production security hardening.
- Clinic credential verification and legal/privacy compliance workflows.

Demo providers are fictional sample records. No real businesses are represented. Booking requests are not confirmed appointments. The frontend uses generated CSS artwork rather than real provider photography.

## Tests
From `backend` after installing `requirements.txt`:
```powershell
.venv\Scripts\python.exe -m pytest -q
```

The original API test suite is included. Run it locally after setup; this archive has not been validated on your specific Windows laptop.
