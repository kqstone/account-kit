import { FormEvent, useEffect, useState } from "react"
import { AccountApiError, ensureAccountStyle, type AccountClient, type AccountUser } from "./client"

function messageOf(error: unknown) {
  if (error instanceof AccountApiError) return error.message || "请求失败"
  if (error instanceof Error) return error.message
  return "请求失败"
}

export function LoginForm({
  client,
  deviceName,
  onSuccess,
}: {
  client: AccountClient
  deviceName?: string
  onSuccess: (token: string) => void
}) {
  ensureAccountStyle()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [force, setForce] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setBusy(true)
    try {
      const token = await client.login(username.trim(), password, {
        force,
        deviceName: deviceName || undefined,
      })
      onSuccess(token.access_token)
    } catch (err) {
      const body = err instanceof AccountApiError ? err.body : null
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail?: { code?: string; device_name?: string } }).detail
          : null
      if (err instanceof AccountApiError && err.status === 409 && detail?.code === "ALREADY_LOGGED_IN") {
        setForce(true)
        setError(`该账号已在${detail.device_name || "其他设备"}登录，再次提交将挤掉该设备`)
      } else {
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
