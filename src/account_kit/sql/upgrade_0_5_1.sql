-- account-kit 0.5.0 -> 0.5.1 (PostgreSQL). Idempotent: safe to run repeatedly.
-- Adds auth.users.password_set. Existing accounts get true (they know their password).
-- Hosts write password_set = false when auto-provisioning accounts (e.g. SSO), so the
-- user can later "set" a password with an email code instead of the old password.

ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS password_set BOOLEAN NOT NULL DEFAULT true;
