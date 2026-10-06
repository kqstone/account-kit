import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef, type FormEvent, type ReactNode } from "react"
import { ensureAccountStyle, type AccountClient, type AccountUser } from "./client"
import { resolveProfileLabels, type ProfileLabels } from "./labels"
import { interpolate, messageOf, type DeepPartial } from "./utils"

/** Split a single "2FA code" input into a TOTP code or a recovery code. */
export function splitSecondFactor(value: string) {
  const cleaned = value.trim()
  if (!cleaned) return { code: "", recoveryCode: "" }
  return /^\d[\d\s]*$/.test(cleaned) ? { code: cleaned.replace(/\s+/g, ""), recoveryCode: "" } : { code: "", recoveryCode: cleaned }
}

/** Resend countdown (seconds). */
export function useCountdown(): [number, (seconds: number) => void] {
  const [left, setLeft] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const start = useCallback((seconds: number) => {
    if (timer.current) clearInterval(timer.current)
    setLeft(Math.max(0, Math.floor(seconds)))
    timer.current = setInterval(() => {
      setLeft((value) => {
        if (value <= 1) {
          if (timer.current) clearInterval(timer.current)
          timer.current = null
          return 0
        }
        return value - 1
      })
    }, 1000)
  }, [])
  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current)
    },
    [],
  )
  return [left, start]
}

export type CaptchaImageHandle = { reload: () => Promise<void> }

/** Image captcha (``client.captcha()``): click the image to reload; ``onCaptchaId`` gets each new id. */
export const CaptchaImage = forwardRef<
  CaptchaImageHandle,
  {
    client: AccountClient
    value: string
    onChange: (value: string) => void
    onCaptchaId: (captchaId: string) => void
    onError?: (error: unknown) => void
    language?: string
    labels?: DeepPartial<ProfileLabels> | null
  }
>(function CaptchaImage({ client, value, onChange, onCaptchaId, onError, language = "zh", labels }, ref) {
  ensureAccountStyle()
  const L = useMemo(() => resolveProfileLabels(language, labels), [language, labels])
  const [image, setImage] = useState("")
  const [error, setError] = useState("")

  const reload = useCallback(async () => {
    setError("")
    onChange("")
    try {
      const data = await client.captcha()
      setImage(data.image_base64 ? `data:image/png;base64,${data.image_base64}` : "")
      onCaptchaId(data.captcha_id || "")
    } catch (e) {
      setImage("")
      setError(L.captchaLoadFailed)
      onError?.(e)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, L])

  useImperativeHandle(ref, () => ({ reload }), [reload])
  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client])

  return (
    <label className="ak-field">
      {L.captcha}
      <span className="ak-row">
        <input className="ak-input" value={value} autoComplete="off" placeholder={L.captchaPlaceholder} onChange={(event) => onChange(event.target.value)} />
        {image ? (
          <img className="ak-captcha-img" src={image} alt="captcha" title={L.captchaRefresh} onClick={() => void reload()} />
        ) : (
          <button type="button" className="ak-link" onClick={() => void reload()}>
            {L.captchaRefresh}
          </button>
        )}
      </span>
      {error ? <p className="ak-error">{error}</p> : null}
    </label>
  )
})

/** Verified email change: code to the new address (POST /me/email/send-code), then POST /me/email. */
export function ChangeEmailForm({
  client,
  token,
  user,
  language = "zh",
  labels,
  requirePassword = true,
  className = "",
  onChanged,
  onError,
}: {
  client: AccountClient
  token: string
  user?: AccountUser | null
  language?: string
  labels?: DeepPartial<ProfileLabels> | null
  requirePassword?: boolean
  className?: string
  onChanged?: (user: AccountUser) => void
  onError?: (error: unknown) => void
}) {
  ensureAccountStyle()
  const L = useMemo(() => resolveProfileLabels(language, labels), [language, labels])
  const [newEmail, setNewEmail] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [left, start] = useCountdown()

  async function sendCode() {
    setError("")
    setInfo("")
    setSending(true)
    try {
      const sent = await client.sendChangeEmailCode(token, newEmail.trim(), { language })
      setInfo(interpolate(L.codeSentTo, { email: sent.email || newEmail.trim() }))
      start(sent.cooldown || 60)
    } catch (e) {
      setError(messageOf(e, L.error))
      onError?.(e)
    } finally {
      setSending(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setInfo("")
    setBusy(true)
    try {
      const updated = await client.changeEmail(token, newEmail.trim(), code.trim(), password || undefined)
      setInfo(L.emailChanged)
      setCode("")
      setPassword("")
      onChanged?.(updated)
    } catch (e) {
      setError(messageOf(e, L.error))
      onError?.(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className={["ak-form", className].filter(Boolean).join(" ")} onSubmit={submit}>
      {user?.email ? <p className="ak-muted">{`${L.currentEmail}: ${user.email}`}</p> : null}
      <label>
        {L.newEmail}
        <input type="email" value={newEmail} autoComplete="email" onChange={(event) => setNewEmail(event.target.value)} />
      </label>
      <div className="ak-row">
        <input className="ak-input" value={code} maxLength={6} inputMode="numeric" placeholder={L.emailCodePlaceholder} onChange={(event) => setCode(event.target.value)} />
        <button type="button" disabled={sending || left > 0 || !newEmail.trim()} onClick={() => void sendCode()}>
          {sending ? L.sending : left > 0 ? interpolate(L.resendIn, { s: left }) : L.sendCode}
        </button>
      </div>
      {requirePassword ? (
        <label>
          {L.oldPassword}
          <input type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
        </label>
      ) : null}
      {error ? <p className="ak-error">{error}</p> : null}
      {info ? <p className="ak-success">{info}</p> : null}
      <button type="submit" disabled={busy || !code.trim()}>
        {busy ? L.saving : L.confirmChangeEmail}
      </button>
    </form>
  )
}

/** Self-service account deletion (server ``self_delete_enabled``). */
export function DeleteAccountForm({
  client,
  token,
  language = "zh",
  labels,
  twoFactorEnabled = false,
  emailCodeAvailable = false,
  className = "",
  onDeleted,
  onError,
}: {
  client: AccountClient
  token: string
  language?: string
  labels?: DeepPartial<ProfileLabels> | null
  /** Show the 2FA input (pass ``TwoFactorStatus.enabled``). */
  twoFactorEnabled?: boolean
  /** Offer an emailed code instead of TOTP (server ``two_factor_email_enabled``). */
  emailCodeAvailable?: boolean
  className?: string
  onDeleted?: (result: { status: string; detail?: string }) => void
  onError?: (error: unknown) => void
}) {
  ensureAccountStyle()
  const L = useMemo(() => resolveProfileLabels(language, labels), [language, labels])
  const [password, setPassword] = useState("")
  const [factor, setFactor] = useState("")
  const [emailCode, setEmailCode] = useState("")
  const [ack, setAck] = useState(false)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [left, start] = useCountdown()

  async function sendEmail() {
    setError("")
    setSending(true)
    try {
      const sent = await client.sendDeleteAccountEmailCode(token, language)
      start(sent.cooldown || 60)
    } catch (e) {
      setError(messageOf(e, L.error))
    } finally {
      setSending(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setBusy(true)
    try {
      const result = await client.deleteAccount(token, {
        password,
        ...splitSecondFactor(factor),
        emailCode: emailCode.trim() || undefined,
      })
      onDeleted?.(result)
    } catch (e) {
      setError(messageOf(e, L.error))
      onError?.(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className={["ak-form", "ak-danger-zone", className].filter(Boolean).join(" ")} onSubmit={submit}>
      <h3 style={{ margin: 0, fontSize: 15 }}>{L.deleteAccount}</h3>
      <p className="ak-warn">{L.deleteAccountHint}</p>
      <label>
        {L.oldPassword}
        <input type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {twoFactorEnabled ? (
        <label>
          {L.twoFactorCode}
          <input value={factor} autoComplete="one-time-code" onChange={(event) => setFactor(event.target.value)} />
        </label>
      ) : null}
      {twoFactorEnabled && emailCodeAvailable ? (
        <div className="ak-row">
          <input className="ak-input" value={emailCode} maxLength={6} placeholder={L.emailCodePlaceholder} onChange={(event) => setEmailCode(event.target.value)} />
          <button type="button" disabled={sending || left > 0} onClick={() => void sendEmail()}>
            {sending ? L.sending : left > 0 ? interpolate(L.resendIn, { s: left }) : L.sendCode}
          </button>
        </div>
      ) : null}
      <label className="ak-check">
        <input type="checkbox" checked={ack} onChange={(event) => setAck(event.target.checked)} />
        {L.deleteAccountTyped}
      </label>
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" className="ak-btn ak-btn-danger" disabled={busy || !ack || !password}>
        {L.deleteAccountConfirm}
      </button>
    </form>
  )
}

/** Calls the kit logout (revokes the session and refresh token), then ``onDone`` even on network errors. */
export function LogoutButton({
  client,
  token,
  refreshToken,
  allDevices = false,
  language = "zh",
  labels,
  className = "",
  children,
  onDone,
}: {
  client: AccountClient
  token?: string | null
  refreshToken?: string | null
  allDevices?: boolean
  language?: string
  labels?: DeepPartial<ProfileLabels> | null
  className?: string
  children?: ReactNode
  onDone?: (error: unknown) => void
}) {
  ensureAccountStyle()
  const L = useMemo(() => resolveProfileLabels(language, labels), [language, labels])
  const [busy, setBusy] = useState(false)
  async function run() {
    setBusy(true)
    let failure: unknown = null
    try {
      await client.logout(token || null, { refreshToken: refreshToken || null, allDevices })
    } catch (e) {
      failure = e
    } finally {
      setBusy(false)
      onDone?.(failure)
    }
  }
  return (
    <button type="button" className={["ak-btn", "ak-btn-outline", className].filter(Boolean).join(" ")} disabled={busy} onClick={() => void run()}>
      {children ?? (busy ? L.loggingOut : allDevices ? L.logoutAll : L.logout)}
    </button>
  )
}
