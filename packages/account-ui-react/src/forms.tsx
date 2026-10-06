import { useEffect, useState, type FormEvent } from "react"
import { AccountApiError, ensureAccountStyle, type AccountClient, type AccountUser, type TokenPair } from "./client"
import { getMfaChallenge, type MfaChallenge } from "./mfa"

function messageOf(error: unknown) {
  if (error instanceof AccountApiError) return error.message || "请求失败"
  if (error instanceof Error) return error.message
  return "请求失败"
}

export function LoginForm({
  client,
  deviceName,
  trustedDeviceToken,
  onSuccess,
  onTokens,
  onMfa,
}: {
  client: AccountClient
  deviceName?: string
  trustedDeviceToken?: string | ((username: string) => string)
  onSuccess: (token: string) => void
  /** Full login response (includes ``refresh_token`` when the server enables refresh tokens). */
  onTokens?: (tokens: TokenPair) => void
  onMfa?: (challenge: MfaChallenge & { username: string; password: string; force: boolean }) => void
}) {
  ensureAccountStyle()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [force, setForce] = useState(false)
  // Image captcha (428 CAPTCHA_REQUIRED after repeated failures, when the host enables it)
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
      setError("验证码加载失败，请点击换一张")
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    if (captchaNeeded && (!captchaId || !captchaCode.trim())) {
      setError("请输入图形验证码")
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
      // A captcha is single-use: any reply after sending one needs a fresh image.
      if (usedCaptcha) setCaptchaNeeded(false)
      if (status === 428 || code === "CAPTCHA_REQUIRED" || code === "CAPTCHA_INVALID" || info?.captcha_required) {
        setCaptchaNeeded(true)
        await loadCaptcha()
        setError(
          code === "CAPTCHA_INVALID"
            ? "图形验证码错误或已失效，请重试"
            : status === 428 || code === "CAPTCHA_REQUIRED"
              ? "请输入图形验证码"
              : messageOf(err),
        )
      } else if (status === 409 && code === "ALREADY_LOGGED_IN") {
        setForce(true)
        setError(`该账号已在${info?.device_name || "其他设备"}登录，再次提交将挤掉该设备`)
      } else {
        const mfa = getMfaChallenge(err)
        if (mfa && onMfa) {
          onMfa({ ...mfa, username, password, force })
          return
        }
        setError(messageOf(err))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        用户名
        <input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label>
        密码
        <input type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {captchaNeeded ? (
        <label>
          图形验证码
          <span className="ak-row">
            <input
              value={captchaCode}
              autoComplete="off"
              placeholder="输入图中字符"
              onChange={(event) => setCaptchaCode(event.target.value)}
            />
            {captchaImage ? (
              <img src={captchaImage} alt="captcha" style={{ height: 36, cursor: "pointer" }} onClick={() => void loadCaptcha()} />
            ) : null}
            <button type="button" onClick={() => void loadCaptcha()}>
              换一张
            </button>
          </span>
        </label>
      ) : null}
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? "登录中…" : force ? "强制登录" : "登录"}
      </button>
    </form>
  )
}

export function RegisterForm({
  client,
  language = "zh",
  onSuccess,
}: {
  client: AccountClient
  language?: string
  onSuccess: (user: AccountUser) => void
}) {
  ensureAccountStyle()
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
      await client.sendCode(email.trim(), "register", language)
    } catch (err) {
      setError(messageOf(err))
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
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        用户名
        <input value={username} autoComplete="username" onChange={(event) => setUsername(event.target.value)} />
      </label>
      <label>
        邮箱
        <input type="email" value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label>
        密码
        <input type="password" value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      <label>
        姓名（可选）
        <input value={fullName} autoComplete="name" onChange={(event) => setFullName(event.target.value)} />
      </label>
      <label>
        机构（可选）
        <input value={institution} onChange={(event) => setInstitution(event.target.value)} />
      </label>
      <label>
        性别（可选）
        <select value={gender} onChange={(event) => setGender(event.target.value)}>
          <option value="">未指定</option>
          <option value="male">男</option>
          <option value="female">女</option>
        </select>
      </label>
      <label>
        出生年月（可选）
        <input type="month" value={birth} onChange={(event) => setBirth(event.target.value)} />
      </label>
      <div className="ak-row">
        <label>
          验证码
          <input value={code} maxLength={6} inputMode="numeric" onChange={(event) => setCode(event.target.value)} />
        </label>
        <button type="button" disabled={sending} onClick={() => void sendCode()}>
          {sending ? "发送中…" : "发送验证码"}
        </button>
      </div>
      {roles.length ? (
        <label>
          角色
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="">默认</option>
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
        {busy ? "提交中…" : "注册"}
      </button>
    </form>
  )
}

export function ResetPasswordForm({
  client,
  language = "zh",
  onSuccess,
}: {
  client: AccountClient
  language?: string
  onSuccess: () => void
}) {
  ensureAccountStyle()
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
      await client.sendCode(email.trim(), "reset_password", language)
    } catch (err) {
      setError(messageOf(err))
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
      setError(messageOf(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="ak-form" onSubmit={submit}>
      <label>
        邮箱
        <input type="email" value={email} autoComplete="email" onChange={(event) => setEmail(event.target.value)} />
      </label>
      <div className="ak-row">
        <label>
          验证码
          <input value={code} maxLength={6} inputMode="numeric" onChange={(event) => setCode(event.target.value)} />
        </label>
        <button type="button" disabled={sending} onClick={() => void sendCode()}>
          {sending ? "发送中…" : "发送验证码"}
        </button>
      </div>
      <label>
        新密码
        <input type="password" value={password} autoComplete="new-password" onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error ? <p className="ak-error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? "提交中…" : "重置密码"}
      </button>
    </form>
  )
}
