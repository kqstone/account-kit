export type AccountUser = {
  id: string
  username: string
  email: string
  full_name?: string | null
  institution?: string | null
  gender?: string | null
  birth_year_month?: string | null
  role: string
  is_admin: boolean
  is_active: boolean
  approval_status: string
  has_custom_avatar?: boolean
  tier?: string | null
  tier_name?: string | null
  tier_badge_color?: string | null
  pending_role?: string | null
}

export type CaptchaChallenge = { captcha_id: string; image_base64: string; expires_in?: number }

export type CodePurpose = "register" | "reset_password" | "change_password"

export type TwoFactorStatus = {
  enabled: boolean
  enabled_at?: string | null
  recovery_codes_remaining: number
  trusted_devices: number
  email_available: boolean
  trusted_device_days: number
}

export type TwoFactorSetup = { otpauth_uri: string; secret: string }

export type TrustedDevice = {
  id: string
  device_name: string
  created_at?: string | null
  last_used_at?: string | null
  expires_at?: string | null
}

export type LoginSecondFactorResult = {
  access_token: string
  token_type: string
  two_factor_method?: string
  trusted_device_token?: string
  trusted_device_expires_at?: string
  recovery_codes_remaining?: number
}

export type RoleChangeRequest = {
  id: string
  user_id?: string | null
  from_role: string
  to_role: string
  status: string
  created_at?: string | null
}

export type ProfileUpdateResult = {
  user: AccountUser
  access_token?: string | null
  token_type?: string | null
}

export type SecondFactorPayload = {
  password: string
  code?: string
  recoveryCode?: string
  emailCode?: string
}

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

function parseBody(text: string) {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export function createAccountClient(baseUrl: string) {
  const prefix = baseUrl.replace(/\/$/, "")

  async function request(path: string, init: RequestInit = {}, token?: string | null) {
    const headers = new Headers(init.headers)
    if (token) headers.set("Authorization", `Bearer ${token}`)
    if (init.body instanceof FormData) headers.delete("Content-Type")
    const response = await fetch(prefix + path, { ...init, headers })
    const body = parseBody(await response.text())
    if (!response.ok) throw new AccountApiError(detailOf(body, response.statusText), response.status, body)
    return body
  }

  function json(path: string, payload: unknown, token?: string | null, method = "POST") {
    return request(
      path,
      { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
      token,
    )
  }

  return {
    sendCode(email: string, purpose: CodePurpose, language = "zh") {
      return json("/send-code", { email, purpose, language })
    },
    register(payload: Record<string, unknown>) {
      return json("/register", payload) as Promise<AccountUser>
    },
    login(
      username: string,
      password: string,
      extra?: {
        force?: boolean
        deviceName?: string
        trustedDeviceToken?: string
        captchaId?: string
        captchaCode?: string
      },
    ) {
      const form = new URLSearchParams({ username, password })
      if (extra?.force) form.set("force", "true")
      if (extra?.deviceName) form.set("device_name", extra.deviceName)
      if (extra?.trustedDeviceToken) form.set("trusted_device_token", extra.trustedDeviceToken)
      if (extra?.captchaId && extra?.captchaCode) {
        form.set("captcha_id", extra.captchaId)
        form.set("captcha_code", extra.captchaCode)
      }
      return request("/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
      }) as Promise<{ access_token: string; token_type: string }>
    },
    resetPassword(email: string, code: string, newPassword: string) {
      return json("/reset-password", { email, code, new_password: newPassword })
    },
    /** Image captcha served by the host app (GET {prefix}/captcha), required after repeated login failures. */
    captcha() {
      return request("/captcha") as Promise<CaptchaChallenge>
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
    twoFactorStatus(token: string) {
      return request("/2fa/status", {}, token) as Promise<TwoFactorStatus>
    },
    twoFactorSetup(token: string, password?: string) {
      return json("/2fa/setup", password ? { password } : {}, token) as Promise<TwoFactorSetup>
    },
    twoFactorEnable(token: string, code: string) {
      return json("/2fa/enable", { code }, token) as Promise<{ enabled: boolean; recovery_codes: string[] }>
    },
    twoFactorDisable(token: string, payload: SecondFactorPayload) {
      return json(
        "/2fa/disable",
        {
          password: payload.password,
          code: payload.code || "",
          recovery_code: payload.recoveryCode || "",
          email_code: payload.emailCode || "",
        },
        token,
      ) as Promise<{ enabled: boolean }>
    },
    regenerateRecoveryCodes(token: string, payload: SecondFactorPayload) {
      return json(
        "/2fa/recovery-codes/regenerate",
        {
          password: payload.password,
          code: payload.code || "",
          recovery_code: payload.recoveryCode || "",
        },
        token,
      ) as Promise<{ status: string; recovery_codes: string[] }>
    },
    sendDisableEmailCode(token: string, language = "zh") {
      return json("/2fa/disable/email-code", { language }, token) as Promise<{
        status: string
        email?: string
        expires_in?: number
        cooldown?: number
      }>
    },
    listTrustedDevices(token: string) {
      return request("/trusted-devices", {}, token).then(
        (body) => ((body as { devices?: TrustedDevice[] } | null)?.devices || []) as TrustedDevice[],
      )
    },
    revokeTrustedDevice(token: string, deviceId: string) {
      return request(`/trusted-devices/${encodeURIComponent(deviceId)}`, { method: "DELETE" }, token)
    },
    revokeAllTrustedDevices(token: string) {
      return request("/trusted-devices", { method: "DELETE" }, token) as Promise<{ status: string; revoked: number }>
    },
    loginSecondFactor(payload: {
      challengeToken: string
      code?: string
      recoveryCode?: string
      emailCode?: string
      trustDevice?: boolean
      force?: boolean
      deviceName?: string
    }) {
      const form = new URLSearchParams()
      form.set("challenge_token", payload.challengeToken)
      if (payload.code) form.set("code", payload.code)
      if (payload.recoveryCode) form.set("recovery_code", payload.recoveryCode)
      if (payload.emailCode) form.set("email_code", payload.emailCode)
      if (payload.trustDevice) form.set("trust_device", "true")
      if (payload.force) form.set("force", "true")
      if (payload.deviceName) form.set("device_name", payload.deviceName)
      return request("/login/2fa", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
      }) as Promise<LoginSecondFactorResult>
    },
    sendLoginEmailCode(challengeToken: string, language = "zh") {
      return json("/login/2fa/email/send", { challenge_token: challengeToken, language }) as Promise<{
        status: string
        email?: string
        expires_in?: number
        cooldown?: number
      }>
    },
    changePassword(token: string, oldPassword: string, newPassword: string, code?: string) {
      return json(
        "/change-password",
        { old_password: oldPassword, new_password: newPassword, ...(code ? { code } : {}) },
        token,
      ) as Promise<{ status: string; detail: string }>
    },
    patchMe(token: string, payload: Record<string, unknown>) {
      return json("/me", payload, token, "PATCH") as Promise<ProfileUpdateResult>
    },
    uploadAvatar(token: string, file: Blob, filename?: string) {
      const form = new FormData()
      form.append("file", file, filename || (file instanceof File ? file.name : "avatar.jpg"))
      return request("/me/avatar", { method: "POST", body: form }, token) as Promise<AccountUser>
    },
    deleteAvatar(token: string) {
      return request("/me/avatar", { method: "DELETE" }, token) as Promise<AccountUser>
    },
    avatarUrl(userId: string) {
      return `${prefix}/users/${encodeURIComponent(userId)}/avatar`
    },
    async avatarBlob(userId: string, token: string) {
      const response = await fetch(`${prefix}/users/${encodeURIComponent(userId)}/avatar`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const body = parseBody(await response.text())
        throw new AccountApiError(detailOf(body, response.statusText), response.status, body)
      }
      return await response.blob()
    },
    requestRoleChange(token: string, requestedRole: string) {
      return json("/role-change-requests", { requested_role: requestedRole }, token) as Promise<RoleChangeRequest>
    },
    myRoleChangeRequest(token: string) {
      return request("/role-change-requests/me", {}, token) as Promise<RoleChangeRequest | null>
    },
  }
}

export function ensureAccountStyle() {
  if (typeof document === "undefined" || document.getElementById("account-kit-ui")) return
  const style = document.createElement("style")
  style.id = "account-kit-ui"
  style.textContent = `
.ak-form{display:flex;flex-direction:column;gap:12px;max-width:380px;font-family:inherit}
.ak-form label,.ak-field{display:flex;flex-direction:column;gap:4px;font-size:14px}
.ak-form input,.ak-form select,.ak-input{padding:8px 10px;border:1px solid #d0d5dd;border-radius:8px;font:inherit;box-sizing:border-box}
.ak-row{display:flex;gap:8px;align-items:center}
.ak-row .ak-input{flex:1;min-width:0}
.ak-form button{padding:8px 12px;border:0;border-radius:8px;background:#1677ff;color:#fff;cursor:pointer}
.ak-form button[disabled]{opacity:.6;cursor:default}
.ak-error{color:#cf1322;font-size:13px;margin:0}
.ak-badge{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;color:#fff;font-size:12px;line-height:18px}
.ak-btn{padding:8px 14px;border:0;border-radius:8px;background:#1677ff;color:#fff;cursor:pointer;font:inherit;font-size:14px}
.ak-btn[disabled]{opacity:.6;cursor:default}
.ak-btn-outline{background:transparent;border:1px solid #d0d5dd;color:#344054}
.ak-btn-danger{background:#d92d20;color:#fff}
.ak-btn-small{padding:6px 12px;font-size:13px}
.ak-link{background:none;border:0;padding:0;color:#1677ff;cursor:pointer;font:inherit;font-size:13px}
.ak-link.ak-danger{color:#d92d20}
.ak-hint{margin:0;color:#667085;font-size:14px;line-height:1.5}
.ak-muted{color:#98a2b3;font-size:13px;margin:4px 0}
.ak-success{color:#079455;font-size:14px;padding:10px 14px;background:#ecfdf3;border:1px solid #abefc6;border-radius:8px}
.ak-warn{color:#d92d20;font-size:13px;margin:0 0 12px}
.ak-tf{display:flex;flex-direction:column;gap:12px;max-width:560px;font-family:inherit;color:#101828}
.ak-tf-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
.ak-tf h2,.ak-tf h3,.ak-dialog h3{margin:0}
.ak-tf h2{font-size:20px}
.ak-tf h3,.ak-dialog h3{font-size:16px}
.ak-badge-on{background:#ecfdf3;color:#079455}
.ak-badge-off{background:#f2f4f7;color:#667085}
.ak-section{display:flex;flex-direction:column;gap:8px}
.ak-actions{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap;align-items:center}
.ak-check{display:flex;align-items:center;gap:8px;font-size:14px;cursor:pointer}
.ak-codes{list-style:none;padding:16px;margin:0;display:grid;grid-template-columns:repeat(2,minmax(120px,1fr));gap:8px 24px;background:#f9fafb;border:1px dashed #d0d5dd;border-radius:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:15px}
.ak-qr-wrap{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.ak-qr{width:180px;height:180px;background:#fff;padding:8px;border-radius:8px;box-sizing:border-box}
.ak-secret{display:flex;flex-direction:column;gap:4px}
.ak-secret code{font-size:14px;word-break:break-all}
.ak-code{max-width:220px;text-align:center;letter-spacing:6px;font-size:20px}
.ak-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:2000;padding:16px}
.ak-dialog{background:#fff;color:#101828;border:1px solid #e4e7ec;border-radius:12px;padding:24px;width:100%;max-width:400px;box-sizing:border-box;font-family:inherit}
.ak-dialog .ak-code{max-width:none;width:100%}
.ak-links{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin-top:12px}
.ak-device-list{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:10px}
.ak-device-list li{display:flex;justify-content:space-between;align-items:center;gap:12px}
.ak-device-name{font-weight:600;font-size:14px}
.ak-avatar{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;overflow:hidden;background:#e4e7ec;color:#344054;font-weight:600;flex-shrink:0;user-select:none}
.ak-avatar img{width:100%;height:100%;object-fit:cover;display:block}
.ak-avatar-uploader{display:flex;align-items:center;gap:16px;font-family:inherit}
.ak-avatar-btn{cursor:pointer;border:0;padding:0;background:none;border-radius:50%}
.ak-steps{margin:0 0 8px;padding-left:20px;color:#667085;font-size:14px;line-height:1.7}
.ak-devices{margin-top:16px;padding-top:16px;border-top:1px solid #e4e7ec}
.ak-input{width:100%}
`
  document.head.appendChild(style)
}
