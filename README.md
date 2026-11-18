# LUSHORA — Premium Beauty & Wellness Marketplace MVP

LUSHORA is a Windows-first local development MVP for discovering beauty and wellness providers and sending appointment requests.

## Current experience
- Premium editorial-style responsive homepage with LUSHORA's own plum, ivory and champagne visual identity.
- Category navigation for Makeup, Salon, Skin Clinic and Nail Studio.
- City and text search, plus a verified-provider filter.
- Provider cards with services, prices and booking-request form.
- Editorial inspiration section and provider acquisition section.
- FastAPI endpoints for provider discovery, demo data, booking requests and admin summary.

## Run on Windows
1. Install Python 3.11+ and Node.js LTS.
2. Double-click `RUN_LUSHORA.bat` from this folder.
3. Open http://127.0.0.1:5173
4. Use **Load sample listings** to seed local demo providers.
5. API documentation: http://127.0.0.1:8000/docs

## Current limitations — not production-ready
- Customer login, provider onboarding and role-based admin access are not implemented.
- Provider listings currently use demo seed data unless real providers are added to the database.
- Booking creates a request only; it does not reserve live availability or prevent double booking.
- Payments, refunds, WhatsApp/SMS notifications, verified review collection and production deployment are not implemented.
- Some editorial photography is loaded from Unsplash URLs and therefore requires an internet connection.
- Ratings and verification labels shown for seeded providers are sample data, not real endorsements.

## Tech stack
- Frontend: React 19 + Vite
- Backend: FastAPI + SQLAlchemy
- Database: SQLite for local MVP

This is a development prototype. Complete security, privacy, payment, availability and operational testing before public launch.
