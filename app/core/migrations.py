"""
Startup Database Migrations

Runs idempotent ALTER TABLE statements on every boot so existing deployments
automatically receive the new `users` columns (Google OAuth, email verification,
last-login tracking) without a manual migration step.

Safe to run repeatedly:
  - Only adds columns that do not exist yet (checked via information_schema).
  - Only runs when the `users` table already exists (fresh databases are fully
    created by Base.metadata.create_all in the app lifespan).
  - Existing accounts are grandfathered as email_verified = TRUE so nobody is
    locked out by the newly introduced email-verification requirement.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

USER_COLUMN_MIGRATIONS = [
    ("google_id", "VARCHAR(255)"),
    ("avatar_url", "TEXT"),
    ("email_verified", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("verification_token", "VARCHAR(255)"),
    ("verification_expires_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("last_login", "TIMESTAMP WITHOUT TIME ZONE"),
    ("last_login_ip", "VARCHAR(64)"),
    ("last_login_device", "VARCHAR(255)"),
]


async def run_startup_migrations(engine: AsyncEngine) -> None:
    """Add missing columns/indexes to the users table (idempotent)."""
    try:
        async with engine.begin() as conn:
            # Only relevant when the users table already exists (existing DBs).
            table_exists = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'users' AND table_schema = 'public'"
                )
            )
            if not table_exists:
                logger.info("Startup migrations: users table does not exist yet, skipping")
                return

            # ADD COLUMN IF NOT EXISTS is atomic and race-free across multiple
            # app instances starting simultaneously.
            added_email_verified = False
            for column, definition in USER_COLUMN_MIGRATIONS:
                column_exists = await conn.scalar(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'users' AND column_name = :col"
                    ),
                    {"col": column},
                )
                if column_exists:
                    continue

                await conn.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {definition}"
                    )
                )
                logger.info("Startup migrations: added users.%s", column)
                if column == "email_verified":
                    added_email_verified = True

            # Unique index for google_id (PostgreSQL allows multiple NULLs).
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id "
                    "ON users (google_id)"
                )
            )

            if added_email_verified:
                # Grandfather pre-existing accounts: they were created before the
                # verification requirement, so mark them verified. Idempotent.
                await conn.execute(text("UPDATE users SET email_verified = TRUE"))
                logger.info(
                    "Startup migrations: backfilled existing users as email_verified = TRUE"
                )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Startup migrations failed: %s", exc, exc_info=exc)
