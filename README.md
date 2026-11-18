# LUSHORA MVP (Windows-first)

A runnable starter for the LUSHORA beauty and wellness marketplace.

## One-click start
1. Extract the ZIP to a normal writable folder (for example `C:\LUSHORA`).
2. Double-click `RUN_LUSHORA.bat`.
3. First run checks Python and Node.js, installs them through Windows Package Manager (`winget`) if available, creates a Python virtual environment, installs backend/frontend dependencies, then starts both servers and opens the browser.
4. Click **Load demo data** to add sample providers.

## Test
Double-click `TEST_LUSHORA.bat` after setup, or run from `backend`:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## URLs
- Frontend: http://127.0.0.1:5173
- API health: http://127.0.0.1:8000/api/health
- API docs: http://127.0.0.1:8000/docs

## Included now
- Four categories: Makeup, Salon, Skin Clinic, Nail Studio
- Provider discovery and filters by category/city/locality/price/verification
- Provider profile and service menu
- Booking/enquiry request creation
- Admin summary and demo data seed
- React frontend, FastAPI backend, SQLite local database
- API tests and Windows one-click setup/launch scripts

## Not implemented yet (do not treat as production-ready)
- Real user authentication, role-based permissions and provider self-registration
- Live slot locking/concurrency protection and provider calendar management
- Payment gateway, refunds and payouts
- Official WhatsApp Business API integration
- File uploads/portfolio moderation, reviews, memberships and subscriptions
- Production PostgreSQL deployment, backups, monitoring and security hardening
- Legal/privacy/compliance review and clinic credential verification workflow

SQLite is used for local development to keep first-time setup simple. PySpark is deliberately excluded: it is not needed for the transactional marketplace MVP. Analytics/batch processing can be added later if the data volume requires it.
