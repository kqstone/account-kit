-- account-kit 0.3.0 -> 0.4.0 (PostgreSQL). Idempotent: safe to run repeatedly.
-- New tables only in schema "auth"; no existing table or column changes.
-- Equivalent to ``await account_kit.ensure_schema(engine)`` / ``Base.metadata.create_all``.

CREATE SCHEMA IF NOT EXISTS auth;

-- Mini Program openid bindings. Binding key is (app_id, openid); unionid is optional.
CREATE TABLE IF NOT EXISTS auth.wechat_identities (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    app_id VARCHAR(32) NOT NULL,
    openid VARCHAR(64) NOT NULL,
    unionid VARCHAR(64),
    bound_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    CONSTRAINT pk_wechat_identities PRIMARY KEY (id),
    CONSTRAINT uq_wechat_identities_app_id_openid UNIQUE (app_id, openid),
    CONSTRAINT uq_wechat_identities_user_id_app_id UNIQUE (user_id, app_id),
    CONSTRAINT fk_wechat_identities_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_auth_wechat_identities_unionid ON auth.wechat_identities (unionid);

-- QR login / bind tickets. ticket_hash is SHA-256 of the opaque ticket; scene is the
-- WeChat getwxacodeunlimit scene. openid is stored hashed; plaintext openid / session_key
-- are never persisted. payload_cipher holds Fernet JSON (openid after scan, one-shot
-- token body after confirm). mfa_challenge_hash links a bind-existing 2FA challenge.
CREATE TABLE IF NOT EXISTS auth.wechat_login_tickets (
    id UUID NOT NULL,
    ticket_hash VARCHAR(64) NOT NULL,
    scene VARCHAR(32) NOT NULL,
    purpose VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    user_id UUID,
    openid_hash VARCHAR(64),
    created_ip VARCHAR(64),
    device_name VARCHAR(128),
    force BOOLEAN DEFAULT false NOT NULL,
    token_hash VARCHAR(64),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    payload_cipher TEXT,
    mfa_challenge_hash VARCHAR(64),
    CONSTRAINT pk_wechat_login_tickets PRIMARY KEY (id),
    CONSTRAINT uq_wechat_login_tickets_ticket_hash UNIQUE (ticket_hash),
    CONSTRAINT uq_wechat_login_tickets_scene UNIQUE (scene),
    CONSTRAINT fk_wechat_login_tickets_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_auth_wechat_login_tickets_expires_at ON auth.wechat_login_tickets (expires_at);
CREATE INDEX IF NOT EXISTS ix_auth_wechat_login_tickets_mfa_challenge_hash ON auth.wechat_login_tickets (mfa_challenge_hash);
CREATE INDEX IF NOT EXISTS ix_auth_wechat_login_tickets_user_id ON auth.wechat_login_tickets (user_id);
