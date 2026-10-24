import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import {
  AccountApiError,
  ensureAccountStyle,
  type AccountClient,
  type LoginSecondFactorResult,
  type TokenPair,
  type WechatBindStatus,
  type WechatStartResult,
} from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveFormLabels, resolveWechatLabels, type FormLabels, type WechatLabels } from "./labels"
import { getMfaChallenge, type MfaChallenge } from "./mfa"
import { TwoFactorLoginDialog } from "./twoFactor"
import { formatError, interpolate, type DeepPartial } from "./utils"

function imageSrc(data: WechatStartResult) {
  return `data:${data.mime || "image/png"};base64,${data.image_base64}`
}

export function WechatQrLogin({
  client,
  deviceName = "",
  pollMs = 2000,
  force = false,
  language,
  labels,
  formLabels,
  className = "",
  onSuccess,
  onUnbound,
  onConflict,
  onRegistered,
}: {
  client: AccountClient
  deviceName?: string
  pollMs?: number
  force?: boolean
  language?: string
  labels?: DeepPartial<WechatLabels> | null
  formLabels?: DeepPartial<FormLabels> | null
  className?: string
  onSuccess: (token: string, extra?: { tokens?: TokenPair; username?: string }) => void
  onUnbound?: (info: { bindTicket: string }) => void
  onConflict?: (error: unknown) => void
  onRegistered?: (user: unknown) => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const L = useMemo(() => resolveWechatLabels(locale, labels, messages), [locale, labels, messages])
  const F = useMemo(() => resolveFormLabels(locale, formLabels, messages), [locale, formLabels, messages])
  const [phase, setPhase] = useState<"loading" | "qr" | "expired" | "unbound" | "unconfigured" | "error">("loading")
  const [error, setError] = useState("")
  const [started, setStarted] = useState<WechatStartResult | null>(null)
  const [expiresLeft, setExpiresLeft] = useState(0)
  const [scannedName, setScannedName] = useState("")
  const [tab, setTab] = useState<"bind" | "register">("bind")
  const [bindForce, setBindForce] = useState(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [sending, setSending] = useState(false)
  const [busy, setBusy] = useState(false)
  const [mfa, setMfa] = useState<(MfaChallenge & { username?: string }) | null>(null)
  const ticketRef = useRef("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stop() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (tickRef.current) clearInterval(tickRef.current)
    pollRef.current = null
    tickRef.current = null
  }

  async function start() {
    stop()
    setError("")
    setMfa(null)
    setScannedName("")
    setPhase("loading")
    try {
      const data = await client.startWechatLogin({ deviceName, force: force || bindForce })
      setStarted(data)
      ticketRef.current = data.ticket
      setExpiresLeft(Number(data.expires_in) || 120)
      setPhase("qr")
      pollRef.current = setInterval(() => void poll(), Math.max(500, pollMs || 2000))
      tickRef.current = setInterval(() => {
        setExpiresLeft((value) => {
          if (value <= 1) {
            stop()
            setPhase("expired")
            return 0
          }
          return value - 1
        })
      }, 1000)
    } catch (err) {
      const status = err instanceof AccountApiError ? err.status : 0
      const errCode = err instanceof AccountApiError ? err.code : ""
      if (status === 503 || errCode === "WECHAT_NOT_CONFIGURED") {
        setPhase("unconfigured")
        setError(L.notConfigured)
        return
      }
      setPhase("error")
      setError(formatError(err, F, locale))
    }
  }

  async function poll() {
    const ticket = ticketRef.current
    if (!ticket) return
    try {
      const data = await client.wechatLoginStatus(ticket)
      if (data.status === "scanned" && data.username) setScannedName(data.username)
      if (data.status === "unbound") {
        stop()
        setPhase("unbound")
        onUnbound?.({ bindTicket: data.bind_ticket || ticket })
        return
      }
      if (data.status === "expired" || data.status === "cancelled") {
        stop()
        setPhase("expired")
        return
      }
      if (data.access_token) {
        stop()
        onSuccess(data.access_token, { tokens: data as TokenPair })
      }
    } catch (err) {
      setError(formatError(err, F, locale))
    }
  }

  useEffect(() => {
    void start()
    return () => {
      stop()
      const ticket = ticketRef.current
      if (ticket) void client.cancelWechatLogin(ticket).catch(() => undefined)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submitBind(event: FormEvent) {
    event.preventDefault()
    if (busy || !ticketRef.current) return
    setBusy(true)
    setError("")
    try {
      const tokens = await client.wechatBindExisting({
        bindTicket: ticketRef.current,
        username: username.trim(),
        password,
        force: bindForce || force,
        deviceName,
      })
      onSuccess(tokens.access_token, { tokens, username })
    } catch (err) {
      const challenge = getMfaChallenge(err)
      if (challenge) {
        setMfa({ ...challenge, username })
        return
      }
      const status = err instanceof AccountApiError ? err.status : 0
      const codeName = err instanceof AccountApiError ? err.code : ""
      if (status === 409 && codeName === "ALREADY_LOGGED_IN") {
        setBindForce(true)
        onConflict?.(err)
        const detail = (err as AccountApiError).body as { detail?: { device_name?: string } } | null
        setError(interpolate(F.alreadyLoggedIn, { device: detail?.detail?.device_name || F.errors.UNKNOWN_DEVICE }))
        return
      }
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  async function sendRegisterCode() {
    setSending(true)
    setError("")
    try {
      await client.sendCode(email.trim(), "register", locale)
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setSending(false)
    }
  }

  async function submitRegister(event: FormEvent) {
    event.preventDefault()
    if (busy || !ticketRef.current) return
    setBusy(true)
    setError("")
    try {
      const body = await client.wechatRegister({
        bind_ticket: ticketRef.current,
        username: username.trim(),
        email: email.trim(),
        password,
        code: code.trim(),
      })
      if (body && typeof body === "object" && "access_token" in body && (body as TokenPair).access_token) {
        const tokens = body as TokenPair
        onSuccess(tokens.access_token, { tokens })
      } else {
        onRegistered?.(body)
      }
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={["ak-wechat", className].filter(Boolean).join(" ")}>
      <h3>{L.title}</h3>
      {phase === "unconfigured" ? <p className="ak-error">{L.notConfigured}</p> : null}
      {phase === "expired" ? (
        <>
          <p className="ak-hint">{L.expired}</p>
          <button type="button" className="ak-btn" onClick={() => void start()}>
            {L.refresh}
          </button>
        </>
      ) : null}
      {phase === "unbound" ? (
        <>
          <p className="ak-hint">{L.unboundHint}</p>
          <div className="ak-tabs">
            <button type="button" className={tab === "bind" ? "ak-tab ak-tab-active" : "ak-tab"} onClick={() => setTab("bind")}>
              {L.bindExisting}
            </button>
            <button type="button" className={tab === "register" ? "ak-tab ak-tab-active" : "ak-tab"} onClick={() => setTab("register")}>
              {L.registerTab}
            </button>
          </div>
          {tab === "bind" ? (
            <form className="ak-form" onSubmit={submitBind}>
              <label className="ak-field">
                {F.username}
                <input value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} />
              </label>
              <label className="ak-field">
                {F.password}
                <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
              </label>
              {error ? <p className="ak-error">{error}</p> : null}
              <button type="submit" disabled={busy}>
                {busy ? F.loggingIn : bindForce ? F.forceLogin : L.bindExisting}
              </button>
            </form>
          ) : (
            <form className="ak-form" onSubmit={submitRegister}>
              <label className="ak-field">
                {F.username}
                <input value={username} autoComplete="username" onChange={(e) => setUsername(e.target.value)} />
              </label>
              <label className="ak-field">
                {F.email}
                <input type="email" value={email} autoComplete="email" onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label className="ak-field">
                {F.password}
                <input type="password" value={password} autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
              </label>
              <div className="ak-row">
                <label className="ak-field">
                  {F.code}
                  <input value={code} maxLength={6} inputMode="numeric" onChange={(e) => setCode(e.target.value)} />
                </label>
                <button type="button" disabled={sending} onClick={() => void sendRegisterCode()}>
                  {sending ? F.sending : F.sendCode}
                </button>
              </div>
              {error ? <p className="ak-error">{error}</p> : null}
              <button type="submit" disabled={busy}>
                {busy ? F.submitting : F.register}
              </button>
            </form>
          )}
        </>
      ) : null}
      {phase === "qr" || phase === "loading" || phase === "error" ? (
        <>
          <p className="ak-hint">{scannedName ? L.scanned : L.hint}</p>
          {started ? <img className="ak-wechat-qr" src={imageSrc(started)} alt={L.title} /> : null}
          <p className="ak-muted">{interpolate(L.expiresIn, { s: String(expiresLeft) })}</p>
          {phase === "error" && error ? <p className="ak-error">{error}</p> : null}
          <button type="button" className="ak-btn ak-btn-outline" onClick={() => void start()}>
            {L.refresh}
          </button>
        </>
      ) : null}
      {mfa ? (
        <TwoFactorLoginDialog
          client={client}
          challenge={mfa}
          deviceName={deviceName}
          force={bindForce || force}
          language={locale}
          onSuccess={(data: LoginSecondFactorResult) => {
            setMfa(null)
            onSuccess(data.access_token, { tokens: data })
          }}
          onExpired={() => setMfa(null)}
          onCancel={() => setMfa(null)}
        />
      ) : null}
    </div>
  )
}

export function WechatBindSettings({
  client,
  token,
  language,
  labels,
  formLabels,
  className = "",
  pollMs = 2000,
  onUpdated,
}: {
  client: AccountClient
  token: string
  language?: string
  labels?: DeepPartial<WechatLabels> | null
  formLabels?: DeepPartial<FormLabels> | null
  className?: string
  pollMs?: number
  onUpdated?: (status: WechatBindStatus) => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const L = useMemo(() => resolveWechatLabels(locale, labels, messages), [locale, labels, messages])
  const F = useMemo(() => resolveFormLabels(locale, formLabels, messages), [locale, formLabels, messages])
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<WechatBindStatus | null>(null)
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")
  const [qr, setQr] = useState<WechatStartResult | null>(null)
  const [expiresLeft, setExpiresLeft] = useState(0)
  const [expired, setExpired] = useState(false)
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const ticketRef = useRef("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stop() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (tickRef.current) clearInterval(tickRef.current)
    pollRef.current = null
    tickRef.current = null
  }

  async function load() {
    setLoading(true)
    setError("")
    try {
      const next = await client.wechatBindStatus(token)
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
    return () => stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function startBind() {
    stop()
    setError("")
    setInfo("")
    setExpired(false)
    try {
      const data = await client.startWechatBind(token)
      setQr(data)
      ticketRef.current = data.ticket
      setExpiresLeft(Number(data.expires_in) || 120)
      pollRef.current = setInterval(() => void poll(), Math.max(500, pollMs || 2000))
      tickRef.current = setInterval(() => {
        setExpiresLeft((value) => {
          if (value <= 1) {
            stop()
            setExpired(true)
            return 0
          }
          return value - 1
        })
      }, 1000)
    } catch (err) {
      const statusCode = err instanceof AccountApiError ? err.status : 0
      if (statusCode === 503) setError(L.notConfigured)
      else setError(formatError(err, F, locale))
    }
  }

  async function poll() {
    const ticket = ticketRef.current
    if (!ticket) return
    try {
      const data = await client.wechatLoginStatus(ticket)
      if (data.status === "expired" || data.status === "cancelled") {
        stop()
        setExpired(true)
        return
      }
      if (data.status === "confirmed" || data.status === "consumed") {
        stop()
        setQr(null)
        ticketRef.current = ""
        setInfo(L.boundOk)
        await load()
      }
    } catch (err) {
      setError(formatError(err, F, locale))
    }
  }

  async function unbind(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError("")
    try {
      await client.unbindWechat(token, { password, code })
      setPassword("")
      setCode("")
      setInfo(L.unboundOk)
      await load()
    } catch (err) {
      setError(formatError(err, F, locale))
    } finally {
      setBusy(false)
    }
  }

  const bound = !!status?.bound
  return (
    <div className={["ak-tf ak-wechat", className].filter(Boolean).join(" ")}>
      <div className="ak-tf-head">
        <h2>{L.title}</h2>
        <span className={bound ? "ak-badge ak-badge-on" : "ak-badge ak-badge-off"}>{bound ? L.bound : L.unbound}</span>
      </div>
      {loading ? <p className="ak-muted">{L.loading}</p> : null}
      {info ? <p className="ak-success">{info}</p> : null}
      {error ? <p className="ak-error">{error}</p> : null}
      {bound ? (
        <>
          <p className="ak-hint">
            {L.openid}: {status?.openid_masked || ""}
          </p>
          <p className="ak-hint">{L.unbindHint}</p>
          <form className="ak-form" onSubmit={unbind}>
            <label className="ak-field">
              {L.currentPassword}
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="ak-field">
              {F.code}
              <input value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <button type="submit" className="ak-btn ak-btn-danger" disabled={busy}>
              {L.unbindConfirm}
            </button>
          </form>
        </>
      ) : (
        <>
          {qr && !expired ? <img className="ak-wechat-qr" src={imageSrc(qr)} alt={L.bind} /> : null}
          {qr && !expired ? <p className="ak-muted">{interpolate(L.expiresIn, { s: String(expiresLeft) })}</p> : null}
          {expired ? <p className="ak-hint">{L.expired}</p> : null}
          <button type="button" className="ak-btn" onClick={() => void startBind()}>
            {qr ? L.refresh : L.bind}
          </button>
        </>
      )}
    </div>
  )
}
