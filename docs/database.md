# Database

Status: **Implemented** with SQLite/SQLAlchemy and versioned startup migrations.

Tables: users, cameras, camera_zones, camera_sessions, worker_sessions, worker_snapshots, activity_events, event_reviews, system_health_events, customer_sessions, daily_summaries and schema_versions. Media remains on disk; rows store safe relative paths. Track, worker-session, camera-session, camera, event and service-session identifiers remain distinct.

