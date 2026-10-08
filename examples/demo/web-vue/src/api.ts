import { ref, shallowRef } from "vue"
import {
  createAccountClient,
  createTokenStore,
  type AccountClient,
  type AccountUser,
  type TokenPair,
  type TokenStore,
} from "@kqstone/account-ui-vue"
import { demoLocale } from "./i18n"

export const tokenStore: TokenStore = createTokenStore("account-kit:tokens")

export const client: AccountClient = createAccountClient("/api/auth", {
  getToken: tokenStore.getAccessToken,
  getLocale: () => demoLocale.value,
  logoutPath: "/logout",
  autoRefresh: {
    getRefreshToken: tokenStore.getRefreshToken,
    onTokens: tokenStore.set,
    onRefreshFailed: () => {
      tokenStore.clear()
      currentUser.value = null
    },
  },
})

export interface SetupStatus {
  initialized: boolean
  features: Record<string, any> | null
  mail_mode: string | null
  web: string
  error: string | null
}

export interface OutboxItem {
  to: string
  purpose: string
  code: string
  language: string
  at: string
}

export const setupStatus = ref<SetupStatus | null>(null)
export const currentUser = shallowRef<AccountUser | null>(null)
export const outboxDrawerOpen = ref(false)
export const outboxItems = ref<OutboxItem[]>([])
export const outboxLoading = ref(false)

export async function fetchSetupStatus(): Promise<SetupStatus> {
  const res = await fetch("/api/setup/status")
  if (!res.ok) {
    throw new Error(`获取系统状态失败: HTTP ${res.status}`)
  }
  const data: SetupStatus = await res.json()
  setupStatus.value = data
  return data
}

export async function testDb(payload: {
  host: string
  port: number
  user: string
  password?: string
  database: string
}): Promise<{ ok: boolean }> {
  const res = await fetch("/api/setup/test-db", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const msg = body?.detail?.message || (typeof body?.detail === "string" ? body.detail : "数据库连接失败")
    throw new Error(msg)
  }
  return body
}

export async function initSystem(payload: Record<string, any>): Promise<any> {
  const res = await fetch("/api/setup/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const msg = body?.detail?.message || (typeof body?.detail === "string" ? body.detail : "系统初始化失败")
    throw new Error(msg)
  }
  await fetchSetupStatus()
  return body
}

export async function refreshCurrentUser(): Promise<AccountUser | null> {
  const token = tokenStore.getAccessToken()
  if (!token) {
    currentUser.value = null
    return null
  }
  try {
    const user = await client.me(token)
    currentUser.value = user
    return user
  } catch {
    currentUser.value = null
    return null
  }
}

export async function fetchOutbox(email?: string, purpose?: string): Promise<OutboxItem[]> {
  outboxLoading.value = true
  try {
    const params = new URLSearchParams()
    if (email) params.set("email", email)
    if (purpose) params.set("purpose", purpose)
    const qs = params.toString() ? `?${params.toString()}` : ""
    const res = await fetch(`/api/demo/outbox${qs}`)
    if (!res.ok) throw new Error("获取站内信箱失败")
    const data = await res.json()
    outboxItems.value = data.items || []
    return outboxItems.value
  } finally {
    outboxLoading.value = false
  }
}

export async function adminFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = tokenStore.getAccessToken()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json"
  }
  const res = await fetch(path, { ...options, headers })
  if (res.status === 204) return null as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const msg = body?.detail?.message || (typeof body?.detail === "string" ? body.detail : `请求失败 (${res.status})`)
    throw new Error(msg)
  }
  return body as T
}

export async function getAdminUsers(): Promise<AccountUser[]> {
  return adminFetch<AccountUser[]>("/api/admin/account/users")
}

export async function patchAdminUser(userId: string, patch: Record<string, any>): Promise<AccountUser> {
  return adminFetch<AccountUser>(`/api/admin/account/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

export async function resetAdminUser2fa(userId: string): Promise<void> {
  return adminFetch<void>(`/api/admin/account/users/${encodeURIComponent(userId)}/2fa/reset`, {
    method: "POST",
  })
}

export async function deleteAdminUser(userId: string): Promise<void> {
  return adminFetch<void>(`/api/admin/account/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  })
}

export interface AuditLogItem {
  id: string
  user_id: string | null
  event: string
  ip: string
  device_name: string | null
  meta: Record<string, any>
  created_at: string
}

export interface AuditLogsResponse {
  items: AuditLogItem[]
  total: number
  page: number
  page_size: number
}

export async function getAdminAuditLogs(params: {
  page?: number
  page_size?: number
  event?: string
  user_id?: string
  ip?: string
}): Promise<AuditLogsResponse> {
  const sp = new URLSearchParams()
  if (params.page) sp.set("page", String(params.page))
  if (params.page_size) sp.set("page_size", String(params.page_size))
  if (params.event) sp.set("event", params.event)
  if (params.user_id) sp.set("user_id", params.user_id)
  if (params.ip) sp.set("ip", params.ip)
  return adminFetch<AuditLogsResponse>(`/api/admin/account/audit-logs?${sp.toString()}`)
}

export function formatPurposeName(purpose: string): string {
  const map: Record<string, string> = {
    register: "注册验证码",
    reset_password: "重置密码",
    change_password: "修改密码",
    change_email: "修改邮箱",
    login_2fa: "2FA登录",
    disable_2fa: "关闭2FA",
    delete_account: "注销账号",
  }
  return map[purpose] || purpose
}

export function formatDateTime(iso: string): string {
  if (!iso) return "-"
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString("zh-CN", {
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    return iso
  }
}
