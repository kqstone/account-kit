import { useEffect, useMemo, useState, type FormEvent } from "react"
import { AccountApiError, ensureAccountStyle, type AccountClient, type AccountUser, type TokenPair } from "./client"
import { useKitLocale } from "./i18n"
import { resolveFormLabels, type FormLabels } from "./labels"
import { getMfaChallenge, type MfaChallenge } from "./mfa"
import { formatError, interpolate, type DeepPartial } from "./utils"

export function LoginForm({
  client,
  deviceName,
  trustedDeviceToken,
  onSuccess,
  onTokens,
  onMfa,
  language,
  labels,
}: {
  client: AccountClient
  deviceName?: string
  trustedDeviceToken?: string | ((username: string) => string)
  onSuccess: (token: string) => void
  onTokens?: (tokens: TokenPair) => void
  onMfa?: (challenge: MfaChallenge & { username: string; password: string; force: boolean }) => void
  language?: string
  labels?: DeepPartial<FormLabels> | null
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const L = useMemo(() => resolveFormLabels(locale, labels), [locale, labels])
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [force, setForce] = useState(false)
  const [captchaNeeded, setCaptchaNeeded] = useState(false)
  const [captchaId, setCaptchaId] = useState("")
  const [captchaImage, setCaptchaImage] = useState("")
  const [captchaCode, setCaptchaCode] = useState("")

  async function loadCaptcha() {
    setCaptchaId("")
    setCaptchaImage("")
    setCaptchaCode("")
    if (typeof client.captcha !== "function") return
    try {
      const data = await client.captcha()
      setCaptchaId(data.captcha_id || "")
      setCaptchaImage(data.image_base64 ? `data:image/png;base64,${data.image_base64}` : "")
    } catch {
      setError(L.captchaLoadFailed)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    if (captchaNeeded && (!captchaId || !captchaCode.trim())) {
      setError(L.captchaEnter)
      return
    }
    setBusy(true)
    const usedCaptcha = captchaNeeded
    try {
      const name = username.trim()
      const trusted = typeof trustedDeviceToken === "function" ? trustedDeviceToken(name) : trustedDeviceToken
      const token = await client.login(name, password, {
        force,
        deviceName: deviceName || undefined,
        trustedDeviceToken: trusted || undefined,
        captchaId: usedCaptcha ? captchaId : undefined,
        captchaCode: usedCaptcha ? captchaCode.trim() : undefined,
      })
      setCaptchaNeeded(false)
      onTokens?.(token)
      onSuccess(token.access_token)
    } catch (err) {
      const body = err instanceof AccountApiError ? err.body : null
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail?: { code?: string; device_name?: string; captcha_required?: boolean } | string }).detail
          : null
      const info = detail && typeof detail === "object" ? detail : null
      const status = err instanceof AccountApiError ? err.status : 0
      const code = info?.code
      if (usedCaptcha) setCaptchaNeeded(false)
      if (status === 428 || code === "CAPTCHA_REQUIRED" || code === "CAPTCHA_INVALID" || info?.captcha_required) {
        setCaptchaNeeded(true)
        await loadCaptcha()
        setError(
          code === "CAPTCHA_INVALID"
            ? L.captchaInvalid
            : status === 428 || code === "CAPTCHA_REQUIRED"
              ? L.captchaEnter
              : formatError(err, L, locale),
        )
      } else if (status === 409 && code === "ALREADY_LOGGED_IN") {
        setForce(true)
        setError(interpolate(L.alreadyLoggedIn, { device: info?.device_name || L.errors.UNKNOWN_DEVICE }))
      } else {
        const mfa = getMfaChallenge(err)
        if (mfa && onMfa) {
          onMfa({ ...mfa, username, password, force })
          return
        }
        setError(formatError(err, L, locale))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        {L.username}
        <input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label>
        {L.password}
        <input type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {captchaNeeded ? (
        <label>
          {L.captcha}
          <span className="ak-row">
            <input
              value={captchaCode}
              autoComplete="off"
              placeholder={L.captchaPlaceholder}
              onChange={(event) => setCaptchaCode(event.target.value)}
            />
            {captchaImage ? (
              <img src={captchaImage} alt="captcha" style={{ height: 36, cursor: "pointer" }} onClick={() => void loadCaptcha()} />
            ) : null}
            <button type="button" onClick={() => void loadCaptcha()}>
              {L.captchaRefresh}
            </button>
          </span>
        </label>
      ) : null}
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? L.loggingIn : force ? L.forceLogin : L.login}
      </button>
    </form>
  )
}

export function RegisterForm({
  client,
  language,
  labels,
  onSuccess,
}: {
  client: AccountClient
  language?: string
  labels?: DeepPartial<FormLabels> | null
  onSuccess: (user: AccountUser) => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const L = useMemo(() => resolveFormLabels(locale, labels), [locale, labels])
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fullName, setFullName] = useState("")
  const [institution, setInstitution] = useState("")
  const [gender, setGender] = useState("")
  const [birth, setBirth] = useState("")
  const [code, setCode] = useState("")
  const [role, setRole] = useState("")
  const [roles, setRoles] = useState<Array<{ code: string; name: string }>>([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    let alive = true
    client
      .roles()
      .then((items) => {
        if (alive) setRoles(items)
      })
      .catch(() => {
        if (alive) setRoles([])
      })
    return () => {
      alive = false
    }
  }, [client])

  async function sendCode() {
    setError("")
    setSending(true)
    try {
      await client.sendCode(email.trim(), "register", locale)
    } catch (err) {
      setError(formatError(err, L, locale))
    } finally {
      setSending(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setBusy(true)
    try {
      const user = await client.register({
        username: username.trim(),
        email: email.trim(),
        password,
        code: code.trim(),
        full_name: fullName.trim() || undefined,
        institution: institution.trim() || undefined,
        gender: gender || undefined,
        birth_year_month: birth || undefined,
        role: role || undefined,
      })
      onSuccess(user)
    } catch (err) {
      setError(formatError(err, L, locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        {L.username}
        <input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label>
        {L.email}
        <input type="email" value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label>
        {L.password}
        <input type="password" value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      <label>
        {L.fullNameOptional}
        <input value={fullName} autoComplete="name" onChange={(event) => setFullName(event.target.value)} />
      </label>
      <label>
        {L.institutionOptional}
        <input value={institution} onChange={(event) => setInstitution(event.target.value)} />
      </label>
      <label>
        {L.genderOptional}
        <select value={gender} onChange={(event) => setGender(event.target.value)}>
          <option value="">{L.genderUnspecified}</option>
          <option value="male">{L.genderMale}</option>
          <option value="female">{L.genderFemale}</option>
        </select>
      </label>
      <label>
        {L.birthOptional}
        <input type="month" value={birth} onChange={(event) => setBirth(event.target.value)} />
      </label>
      <div className="ak-row">
        <label>
          {L.code}
          <input value={code} maxLength={6} inputMode="numeric" onChange={(event) => setCode(event.target.value)} />
        </label>
        <button type="button" disabled={sending} onClick={() => void sendCode()}>
          {sending ? L.sending : L.sendCode}
        </button>
      </div>
      {roles.length ? (
        <label>
          {L.role}
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="">{L.roleDefault}</option>
            {roles.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? L.submitting : L.register}
      </button>
    </form>
  )
}

export function ResetPasswordForm({
  client,
  language,
  labels,
  onSuccess,
}: {
  client: AccountClient
  language?: string
  labels?: DeepPartial<FormLabels> | null
  onSuccess: () => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const L = useMemo(() => resolveFormLabels(locale, labels), [locale, labels])
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)

  async function sendCode() {
    setError("")
    setSending(true)
    try {
      await client.sendCode(email.trim(), "reset_password", locale)
    } catch (err) {
      setError(formatError(err, L, locale))
    } finally {
      setSending(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setBusy(true)
    try {
      await client.resetPassword(email.trim(), code.trim(), password)
      onSuccess()
    } catch (err) {
      setError(formatError(err, L, locale))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        {L.email}
        <input type="email" value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
      </label>
      <div className="ak-row">
        <label>
          {L.code}
          <input value={code} maxLength={6} inputMode="numeric" onChange={(event) => setCode(event.target.value)} />
        </label>
        <button type="button" disabled={sending} onClick={() => void sendCode()}>
          {sending ? L.sending : L.sendCode}
        </button>
      </div>
      <label>
        {L.newPassword}
        <input type="password" value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? L.submitting : L.resetPassword}
      </button>
    </form>
  )
}
