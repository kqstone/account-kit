-- account-kit 0.4.x -> 0.5.0 (PostgreSQL). Idempotent: safe to run repeatedly.
-- New table only in schema "auth"; no existing table or column changes.
-- Equivalent to ``await account_kit.ensure_schema(engine)`` / ``Base.metadata.create_all``.
-- Hosts that keep sso_idp_enabled=False may skip this script (kit will not query the table).

CREATE SCHEMA IF NOT EXISTS auth;

-- OIDC authorization codes. Clients live in config/env, not in a table.
-- code_hash is SHA-256 of the opaque code; plaintext is never stored.
CREATE TABLE IF NOT EXISTS auth.oauth_authorization_codes (
    id UUID NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    client_id VARCHAR(128) NOT NULL,
    user_id UUID NOT NULL,
    redirect_uri VARCHAR(512) NOT NULL,
    code_challenge VARCHAR(128) NOT NULL,
    code_challenge_method VARCHAR(16) DEFAULT 'S256' NOT NULL,
    nonce VARCHAR(256),
    scope VARCHAR(256),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    access_jti VARCHAR(64),
    replayed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    created_ip VARCHAR(64),
    CONSTRAINT pk_oauth_authorization_codes PRIMARY KEY (id),
    CONSTRAINT uq_oauth_authorization_codes_code_hash UNIQUE (code_hash),
    CONSTRAINT fk_oauth_authorization_codes_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_auth_oauth_authorization_codes_expires_at ON auth.oauth_authorization_codes (expires_at);
CREATE INDEX IF NOT EXISTS ix_auth_oauth_authorization_codes_user_id ON auth.oauth_authorization_codes (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_oauth_authorization_codes_access_jti ON auth.oauth_authorization_codes (access_jti);
