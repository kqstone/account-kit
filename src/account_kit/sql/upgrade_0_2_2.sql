-- account-kit 0.2.1 -> 0.2.2 (PostgreSQL). Idempotent: safe to run repeatedly.
-- Only new tables in schema "auth"; no existing table or column changes.
-- Equivalent to ``await account_kit.ensure_schema(engine)`` / ``Base.metadata.create_all``.

CREATE SCHEMA IF NOT EXISTS auth;

-- Fixed-window counters: send/login rate limits, wrong-code attempts, login failures.
CREATE TABLE IF NOT EXISTS auth.rate_limit_counters (
    key VARCHAR(255) NOT NULL,
    count INTEGER DEFAULT 0 NOT NULL,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_rate_limit_counters PRIMARY KEY (key)
);
CREATE INDEX IF NOT EXISTS ix_auth_rate_limit_counters_expires_at ON auth.rate_limit_counters (expires_at);

-- Pending second login step (state_backend="db").
CREATE TABLE IF NOT EXISTS auth.two_factor_challenges (
    token_hash VARCHAR(64) NOT NULL,
    user_id UUID NOT NULL,
    pw_fp VARCHAR(64) NOT NULL,
    device_name VARCHAR(128),
    attempts INTEGER DEFAULT 0 NOT NULL,
    passed BOOLEAN DEFAULT false NOT NULL,
    method VARCHAR(16),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_two_factor_challenges PRIMARY KEY (token_hash),
    CONSTRAINT fk_two_factor_challenges_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_auth_two_factor_challenges_expires_at ON auth.two_factor_challenges (expires_at);
CREATE INDEX IF NOT EXISTS ix_auth_two_factor_challenges_user_id ON auth.two_factor_challenges (user_id);

-- Refresh tokens (SHA-256 only), rotation families.
CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    family_id UUID NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    session_id VARCHAR(64),
    device_name VARCHAR(128),
    ip VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(32),
    replaced_by UUID,
    CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
    CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash),
    CONSTRAINT fk_refresh_tokens_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_auth_refresh_tokens_user_id ON auth.refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_refresh_tokens_family_id ON auth.refresh_tokens (family_id);

-- Built-in image captcha answers (hashed, single use).
CREATE TABLE IF NOT EXISTS auth.captcha_challenges (
    id VARCHAR(64) NOT NULL,
    answer_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_captcha_challenges PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_auth_captcha_challenges_expires_at ON auth.captcha_challenges (expires_at);

-- auth.auth_audit_logs already exists since 0.1 (created by create_all / host migrations);
-- 0.2.2 starts writing to it. Optional retention job, e.g.:
--   DELETE FROM auth.auth_audit_logs WHERE created_at < now() - interval '180 days';
