export type AccountUser = {
  id: string
  username: string
  email: string
  full_name?: string | null
  institution?: string | null
  role: string
  is_admin: boolean
  is_active: boolean
  approval_status: string
  tier?: string | null
  tier_name?: string | null
  tier_badge_color?: string | null
  pending_role?: string | null
}

export type CodePurpose = "register" | "reset_password" | "change_password"

export class AccountApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = "AccountApiError"
    this.status = status
    this.body = body
  }
}

export type AccountClient = ReturnType<typeof createAccountClient>

function detailOf(body: unknown, fallback: string) {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === "string") return detail
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message: unknown }).message
      if (typeof message === "string") return message
    }
  }
  return fallback
}

export function createAccountClient(baseUrl: string) {
  const prefix = baseUrl.replace(/\/$/, "")

  async function request(path: string, init: RequestInit = {}, token?: string | null) {
    const headers = new Headers(init.headers)
    if (token) headers.set("Authorization", `Bearer ${token}`)
    const response = await fetch(prefix + path, { ...init, headers })
    const text = await response.text()
    const body = text ? JSON.parse(text) : null
    if (!response.ok) throw new AccountApiError(detailOf(body, response.statusText), response.status, body)
    return body
  }

  return {
    sendCode(email: string, purpose: CodePurpose, language = "zh") {
      return request("/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, purpose, language }),
      })
    },
    register(payload: Record<string, unknown>) {
      return request("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }) as Promise<AccountUser>
    },
    login(username: string, password: string, extra?: { force?: boolean; deviceName?: string }) {
      const form = new URLSearchParams({ username, password })
      if (extra?.force) form.set("force", "true")
      if (extra?.deviceName) form.set("device_name", extra.deviceName)
      return request("/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
      }) as Promise<{ access_token: string; token_type: string }>
    },
    resetPassword(email: string, code: string, newPassword: string) {
      return request("/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, new_password: newPassword }),
      })
    },
    me(token: string) {
      return request("/me", {}, token) as Promise<AccountUser>
    },
    roles() {
      return request("/roles") as Promise<Array<{ code: string; name: string }>>
    },
    tiers() {
      return request("/tiers") as Promise<Array<{ code: string; name: string; badge_color?: string | null }>>
    },
  }
}

export function ensureAccountStyle() {
  if (typeof document === "undefined" || document.getElementById("account-kit-ui")) return
  const style = document.createElement("style")
  style.id = "account-kit-ui"
  style.textContent = `
.ak-form{display:flex;flex-direction:column;gap:12px;max-width:380px;font-family:inherit}
.ak-form label{display:flex;flex-direction:column;gap:4px;font-size:14px}
.ak-form input,.ak-form select{padding:8px 10px;border:1px solid #d0d5dd;border-radius:8px;font:inherit}
.ak-row{display:flex;gap:8px;align-items:center}
.ak-form button{padding:8px 12px;border:0;border-radius:8px;background:#1677ff;color:#fff;cursor:pointer}
.ak-form button[disabled]{opacity:.6;cursor:default}
.ak-error{color:#cf1322;font-size:13px;margin:0}
.ak-badge{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;color:#fff;font-size:12px;line-height:18px}
`
  document.head.appendChild(style)
}
