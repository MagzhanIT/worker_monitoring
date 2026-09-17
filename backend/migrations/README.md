# Migrations

The reference build creates schema version 1 on first startup without deleting existing data. Before a pilot, initialize Alembic against the SQLAlchemy metadata and review every generated migration; never auto-drop the database.
## Schema v3

Run from the `backend` directory:

```powershell
.venv\Scripts\python.exe migrations\upgrade_v3.py
```

The upgrade is additive and idempotent. It adds customer-journey, activity
diagnostic, per-camera TEST-mode, worker/customer assignment, service-phase,
and local session-stitch audit storage. It does not delete or rewrite existing
camera, worker, event, snapshot, identity, or report data.
