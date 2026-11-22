# LUSHORA Phase 0 Production Readiness Runbook

**Status:** Prepared; staging/production execution is not evidenced yet.  
**Scope:** Phase 0 deployment controls, migrations, backup/restore, security validation, and rollback.

## 1. Required production environment

Configure through the deployment platform's secret/configuration manager. Do not commit secrets or put them in CI logs.

| Setting | Requirement |
|---|---|
| `APP_ENV` | `production` |
| `LUSHORA_AUTH_SECRET` | Random secret, at least 32 bytes; rotate using an approved token/session invalidation plan |
| `LUSHORA_OTP_DEV_MODE` | `false`; production SMS provider is not implemented/configured in this repository |
| `LUSHORA_CORS_ORIGINS` | Comma-separated exact HTTPS frontend origins; no wildcard or localhost |
| `LUSHORA_DATABASE_URL` | PostgreSQL connection URL |
| `LUSHORA_ADMIN_EMAIL` | Initial administrator email |
| `LUSHORA_ADMIN_PASSWORD` | Strong password meeting application policy |
| `LUSHORA_ADMIN_NAME` | Optional display name |
| `LUSHORA_VERIFICATION_UPLOAD_DIR` | Absolute private directory, outside repository, writable by service, mode 0700 or stricter |
| `LUSHORA_PORTFOLIO_UPLOAD_DIR` | Absolute private directory, outside repository, writable by service, mode 0700 or stricter |
| `LUSHORA_BACKUP_DIR` | Absolute private backup directory, outside repository, writable by service, mode 0700 or stricter |
| `LUSHORA_BACKUP_RETENTION_DAYS` | Integer >= 7 |
| `LUSHORA_PORTFOLIO_UPLOAD_DIR` | Must be configured explicitly; production no longer creates a repository-local default |

Before starting the API, create and secure the three storage directories with the deployment user. Production startup validates their existence, writability, location, and permissions.

## 2. Release procedure

1. Review the exact commit and CI status. Do not deploy a commit with failing checks.
2. Build and publish the backend/frontend artifacts from that commit.
3. Confirm PostgreSQL backup completed and the dump checksum sidecar exists.
4. Run the migration script from `backend`:
   `bash scripts/migrate_production.sh`
5. Confirm the applied Alembic revision equals the repository head migration.
6. Deploy API and frontend. Do not run `demo-seed` in production.
7. Verify API health, login, category/provider discovery, booking request, provider dashboard, admin login, and notification queue health.
8. Verify logs contain no secrets, OTPs, raw identity documents, or full sensitive user payloads.
9. Keep the previous deployment artifact available until smoke tests pass.

## 3. Backup procedure

Required environment variables: `LUSHORA_DATABASE_URL`, `LUSHORA_BACKUP_DIR`, `LUSHORA_BACKUP_RETENTION_DAYS`.

Run:
```bash
cd backend
bash scripts/backup_postgres.sh
```

Confirm the generated `lushora-*.dump` and `.sha256` files exist. Backup storage must be private and should be encrypted at rest by the storage provider or platform. This script does not prove off-site replication or encryption.

## 4. Restore drill

Use an isolated PostgreSQL database, never the production database as a restore target.

Required: `LUSHORA_RESTORE_DATABASE_URL` points to the isolated restore-test database and `BACKUP_FILE` points to the selected dump.

Run:
```bash
cd backend
BACKUP_FILE=/absolute/path/to/lushora-YYYYMMDD-HHMMSS.dump bash scripts/restore_verify_postgres.sh
```

The verifier checks the SHA-256 sidecar, dump readability, applied migration revision, and critical tables. Compare source and restored table row counts and perform application smoke tests. CI exercises a marker and critical table row-count comparison; production-like restore drills still need to be performed and recorded.

## 5. Rollback

- **Application rollback:** deploy the last known-good application artifact. Do not automatically downgrade database schema.
- **Database rollback:** there is no blanket automatic Alembic downgrade guarantee. For destructive or incompatible migrations, restore the pre-migration backup into an isolated database first; validate application compatibility and data integrity; obtain explicit approval for any production restore/cutover.
- Stop writes or use a documented maintenance window if a rollback/restore requires consistency.
- Record incident timeline, migration revision, backup identifier/checksum, validation, decision-maker, and customer impact.

## 6. Monitoring and incident checks

Monitor and alert for:
- API health failures and elevated 5xx/latency.
- Authentication rate-limit events and suspicious failed login/OTP patterns.
- Database connection exhaustion, migration errors, and booking conflict failures.
- Notification delivery queue backlog, retries, exhausted attempts, and worker restarts.
- Backup failures, age of last successful backup, checksum failures, and restore-drill status.
- Upload failures, disk usage, and storage permission errors.

The repository currently provides security audit events and notification worker logging; deployment-level metrics, alerting, retention, on-call ownership, and incident-response contacts must be configured by the hosting environment.

## 7. Pre-production smoke-test checklist

- [ ] Exact production environment settings validated.
- [ ] No development OTP or demo seed enabled.
- [ ] Admin bootstrap credential stored safely and rotated after initial setup.
- [ ] PostgreSQL migration and rollback plan reviewed.
- [ ] Backup and checksum verified.
- [ ] Isolated restore drill completed and recorded.
- [ ] Customer login/profile/discovery/booking/cancellation tested.
- [ ] Provider onboarding/verification/services/availability/booking management tested.
- [ ] Admin authentication/verification/moderation tested.
- [ ] Payment gateway sandbox tested; no real money without approved live configuration.
- [ ] Notifications tested with provider sandbox/credentials and consent enabled.
- [ ] Accessibility keyboard/focus/contrast review completed.
- [ ] Mobile/tablet responsive review completed.
- [ ] Monitoring, alert routing, incident contacts, RPO/RTO and rollback decision documented.

## 8. Evidence required for Phase 0 sign-off

CI green at latest branch commit; dependency scans green; browser journeys green; accessibility scan results reviewed; PostgreSQL migration/backup/restore CI drill green; production configuration validated; staging smoke tests recorded; production-like restore drill recorded; and remaining external integration/deployment blockers explicitly accepted by the project owner.
