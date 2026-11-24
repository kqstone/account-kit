-- account-kit 0.6.0 -> 0.7.0 (PostgreSQL). Idempotent: safe to run repeatedly.
-- Approval decision columns on auth.users, plus auth.bind_tickets for SSO bind tickets.
-- Equivalent to ``await account_kit.ensure_schema(engine)`` / ``Base.metadata.create_all``.

CREATE SCHEMA IF NOT EXISTS auth;

ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS approval_reason TEXT;
ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS approval_decided_by VARCHAR(255);
ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS approval_decided_at TIMESTAMP WITH TIME ZONE;

-- SSO bind tickets. ticket_hash is SHA-256 of the opaque ticket; plaintext is never stored.
-- payload_cipher holds Fernet JSON (IdP issuer/sub/email/name). mfa_challenge_hash links a 2FA challenge.
CREATE TABLE IF NOT EXISTS auth.bind_tickets (
    id UUID NOT NULL,
    ticket_hash VARCHAR(64) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    user_id UUID,
    created_ip VARCHAR(64),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    payload_cipher TEXT,
    mfa_challenge_hash VARCHAR(64),
    CONSTRAINT pk_bind_tickets PRIMARY KEY (id),
    CONSTRAINT uq_bind_tickets_ticket_hash UNIQUE (ticket_hash),
    CONSTRAINT fk_bind_tickets_user_id_users FOREIGN KEY (user_id) REFERENCES auth.users (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_auth_bind_tickets_expires_at ON auth.bind_tickets (expires_at);
CREATE INDEX IF NOT EXISTS ix_auth_bind_tickets_mfa_challenge_hash ON auth.bind_tickets (mfa_challenge_hash);
CREATE INDEX IF NOT EXISTS ix_auth_bind_tickets_user_id ON auth.bind_tickets (user_id);
