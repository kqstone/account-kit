-- account-kit 0.2.2 -> 0.2.3 (PostgreSQL). Idempotent: safe to run repeatedly.
-- Partial unique index: at most one row with is_admin = true.
-- If the database already has more than one admin, index creation is skipped
-- with a WARNING (not an error). Fix by keeping exactly one is_admin=true:
--
--   SELECT id, username, email FROM auth.users WHERE is_admin = true;
--   -- set extras to false, then:
--   CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_admin
--     ON auth.users (is_admin) WHERE is_admin = true;
--
-- Equivalent to the index step of ``await account_kit.ensure_schema(engine)``.

DO $$
DECLARE
  admin_count integer;
BEGIN
  IF to_regclass('auth.users') IS NULL THEN
    RETURN;
  END IF;
  SELECT count(*) INTO admin_count FROM auth.users WHERE is_admin = true;
  IF admin_count > 1 THEN
    RAISE WARNING
      'account-kit: skip unique index uq_users_single_admin (% admin rows). Keep exactly one is_admin=true, then CREATE UNIQUE INDEX uq_users_single_admin ON auth.users (is_admin) WHERE is_admin = true;',
      admin_count;
  ELSE
    EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_admin ON auth.users (is_admin) WHERE is_admin = true';
  END IF;
END $$;
