import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { BindExistingAccountForm } from "./bindExisting"
import {
  ensureAccountStyle,
  type AccountClient,
  type AccountUser,
  type SsoBindingStatus,
  type SsoIdentity,
  type TokenPair,
} from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import {
  resolveApprovalLabels,
  resolveFormLabels,
  resolveSsoLabels,
  type ApprovalLabels,
  type FormLabels,
  type SsoLabels,
} from "./labels"
import { formatError, interpolate, type DeepPartial } from "./utils"

export function ApprovalStatusBadge({
  status,
  language,
  labels,
  className = "",
}: {
  status?: string | null
  language?: string
  labels?: DeepPartial<ApprovalLabels> | null
  className?: string
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const L = useMemo(() => resolveApprovalLabels(locale, labels, messages), [locale, labels, messages])
  const key = String(status || "approved").trim().toLowerCase()
  const text = key === "pending" ? L.pending : key === "rejected" ? L.rejected : L.approved
  const tone = key === "pending" ? "ak-approval-pending" : key === "rejected" ? "ak-approval-rejected" : "ak-approval-approved"
  return <span className={["ak-badge", tone, className].filter(Boolean).join(" ")}>{text}</span>
}

export function SsoBindPanel({
  client,
  bindTicket,
  expiresIn = 600,
  identity,
  allowCreate = true,
  matchedUsername = "",
  deviceName = "",
  force = false,
  language,
  labels,
  formLabels,
  className = "",
  onSuccess,
  onPending,
  onExpired,
  onConflict,
}: {
  client: AccountClient
  bindTicket: string
  expiresIn?: number
  identity?: SsoIdentity | null
  allowCreate?: boolean
  matchedUsername?: string
  deviceName?: string
  force?: boolean
  language?: string
  labels?: DeepPartial<SsoLabels> | null
  formLabels?: DeepPartial<FormLabels> | null
  className?: string
  onSuccess: (token: string, extra?: { tokens?: TokenPair; username?: string }) => void
  onPending?: (user: AccountUser) => void
  onExpired?: () => void
  onConflict?: (error: unknown) => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const L = useMemo(() => resolveSsoLabels(locale, labels, messages), [locale, labels, messages])
  const F = useMemo(() => resolveFormLabels(locale, formLabels, messages), [locale, formLabels, messages])
  const [tab, setTab] = useState<"bind" | "create">(allowCreate ? "bind" : "bind")
  const [left, setLeft] = useState(Math.max(0, Number(expiresIn) || 0))
  const [expired, setExpired] = useState(left <= 0)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setLeft(Math.max(0, Number(expiresIn) || 0))
    setExpired((Number(expiresIn) || 0) <= 0)
  }, [expiresIn, bindTicket])

  useEffect(() => {
    if (tickRef.current) clearInterval(tickRef.current)
    if (expired) return
    tickRef.current = setInterval(() => {
      setLeft((value) => {
        if (value <= 1) {
          if (tickRef.current) clearInterval(tickRef.current)
          setExpired(true)
          return 0
        }
        return value - 1
      })
    }, 1000)
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
    }
  }, [expired, bindTicket])

  async function createAccount() {
    if (busy || expired || !bindTicket) return
    setBusy(true)
    setError("")
    try {
      const body = await client.ssoCreateAccount({ bindTicket, force, deviceName })
      if (body && typeof body === "object" && "status" in body && (body as { status?: string }).status === "pending") {
        onPending?.((body as { user: AccountUser }).user)
        return
      }
      const tokens = body as TokenPair
      if (tokens?.access_token) onSuccess(tokens.access_token, { tokens })
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  const email = identity?.email || ""
  const name = identity?.name || ""

  return (
    <div className={["ak-wechat", className].filter(Boolean).join(" ")}>
      <h3>{L.bindTitle}</h3>
      <p className="ak-hint">{L.bindHint}</p>
      <p className="ak-muted">
        {L.identityLabel}
        {name ? ` · ${L.identityName}: ${name}` : ""}
        {email ? ` · ${L.identityEmail}: ${email}` : ""}
      </p>
      {expired ? (
        <>
          <p className="ak-error">{L.ticketExpired}</p>
          <button type="button" className="ak-btn" onClick={() => onExpired?.()}>
            {L.backToLogin}
          </button>
        </>
      ) : (
        <>
          <p className="ak-muted">{interpolate(L.ticketExpiresIn, { s: String(left) })}</p>
          <div className="ak-tabs">
            <button
              type="button"
              className={tab === "bind" ? "ak-tab ak-tab-active" : "ak-tab"}
              onClick={() => setTab("bind")}
            >
              {L.bindExisting}
            </button>
            {allowCreate ? (
              <button
                type="button"
                className={tab === "create" ? "ak-tab ak-tab-active" : "ak-tab"}
                onClick={() => setTab("create")}
              >
                {L.createAccount}
              </button>
            ) : null}
          </div>
          {tab === "bind" ? (
            <BindExistingAccountForm
              client={client}
              bindTicket={bindTicket}
              bindExisting={(payload) => client.ssoBindExisting(payload)}
              deviceName={deviceName}
              force={force}
              language={locale}
              labels={formLabels}
              ssoLabels={labels}
              defaultUsername={matchedUsername || identity?.matched_username || ""}
              usernameLabel={L.usernameOrEmail}
              submitLabel={L.bindExisting}
              allowReclaim
              completeMfaViaLogin2fa={false}
              onSuccess={onSuccess}
              onConflict={onConflict}
            />
          ) : allowCreate ? (
            <div className="ak-form">
              <p className="ak-hint">{interpolate(L.createConfirm, { email: email || "—" })}</p>
              {error ? <p className="ak-error">{error}</p> : null}
              <button type="button" className="ak-btn" disabled={busy} onClick={() => void createAccount()}>
                {busy ? F.submitting : L.createAccount}
              </button>
            </div>
          ) : (
            <p className="ak-hint">{L.createDisabled}</p>
          )}
        </>
      )}
    </div>
  )
}

export function SsoBindSettings({
  client,
  token,
  passwordSet = true,
  language,
  labels,
  formLabels,
  className = "",
  onUpdated,
  onBindStart,
  onNeedPassword,
}: {
  client: AccountClient
  token: string
  passwordSet?: boolean
  language?: string
  labels?: DeepPartial<SsoLabels> | null
  formLabels?: DeepPartial<FormLabels> | null
  className?: string
  onUpdated?: (status: SsoBindingStatus) => void
  onBindStart?: (url: string) => void
  onNeedPassword?: () => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const L = useMemo(() => resolveSsoLabels(locale, labels, messages), [locale, labels, messages])
  const F = useMemo(() => resolveFormLabels(locale, formLabels, messages), [locale, formLabels, messages])
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<SsoBindingStatus | null>(null)
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)

  async function load() {
    setLoading(true)
    setError("")
    try {
      const next = await client.ssoBinding(token)
      setStatus(next)
      onUpdated?.(next)
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function startBind() {
    setError("")
    setInfo("")
    setBusy(true)
    try {
      const data = await client.ssoBindStart(token)
      const url = data?.url
      if (!url) throw new Error(L.error)
      if (onBindStart) onBindStart(url)
      else if (typeof window !== "undefined") window.location.assign(url)
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  async function unbind(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (passwordSet === false) {
      onNeedPassword?.()
      setError(L.unbindNeedPassword)
      return
    }
    setBusy(true)
    setError("")
    try {
      const next = await client.ssoUnbind(token, { password, code })
      setPassword("")
      setCode("")
      setInfo(L.unboundOk)
      setStatus(next)
      onUpdated?.(next)
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  const bound = !!status?.bound
  const canUnbind = passwordSet !== false

  return (
    <div className={["ak-tf ak-wechat", className].filter(Boolean).join(" ")}>
      <div className="ak-tf-head">
        <h2>{L.section}</h2>
        <span className={bound ? "ak-badge ak-badge-on" : "ak-badge ak-badge-off"}>{bound ? L.bound : L.unbound}</span>
      </div>
      {loading ? <p className="ak-muted">{L.loading}</p> : null}
      {info ? <p className="ak-success">{info}</p> : null}
      {error ? <p className="ak-error">{error}</p> : null}
      {bound ? (
        <>
          <p className="ak-hint">
            {L.emailMasked}: {status?.email_masked || ""}
          </p>
          {canUnbind ? <p className="ak-hint">{L.unbindHint}</p> : <p className="ak-warn">{L.unbindNeedPassword}</p>}
          <form className="ak-form" onSubmit={unbind}>
            <label className="ak-field">
              {L.currentPassword}
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} disabled={!canUnbind} />
            </label>
            <label className="ak-field">
              {F.code}
              <input value={code} onChange={(e) => setCode(e.target.value)} disabled={!canUnbind} />
            </label>
            <button type="submit" className="ak-btn ak-btn-danger" disabled={busy || !canUnbind}>
              {L.unbindConfirm}
            </button>
          </form>
        </>
      ) : (
        <button type="button" className="ak-btn" disabled={busy} onClick={() => void startBind()}>
          {L.bind}
        </button>
      )}
    </div>
  )
}
