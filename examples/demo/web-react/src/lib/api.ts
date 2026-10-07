import { tokenStore } from './auth'
import type {
  AdminUserItem,
  AuditLogsResponse,
  OutboxResponse,
  SetupStatusResponse,
} from '../types'

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  const res = await fetch('/api/setup/status')
  if (!res.ok) {
    throw new Error(`获取状态失败: ${res.statusText}`)
  }
  return res.json()
}

export async function testDatabase(db: {
  host: string
  port: number
  user: string
  password?: string
  database: string
}): Promise<{ ok: boolean }> {
  const res = await fetch('/api/setup/test-db', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(db),
  })
  const data = await res.json()
  if (!res.ok) {
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '连接失败'
        : data.detail || '连接失败'
    throw new Error(msg)
  }
  return data
}

export async function initSetup(payload: {
  db: {
    host: string
    port: number
    user: string
    password?: string
    database: string
  }
  admin: {
    username: string
    email: string
    password: string
  }
  features: Record<string, unknown>
  mail_mode: string
}): Promise<{
  initialized: boolean
  admin: { username: string; email: string }
  features: Record<string, unknown>
  mail_mode: string
}> {
  const res = await fetch('/api/setup/init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) {
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '初始化失败'
        : data.detail || '初始化失败'
    throw new Error(msg)
  }
  return data
}

export async function getOutbox(
  email?: string,
  purpose?: string
): Promise<OutboxResponse> {
  const params = new URLSearchParams()
  if (email) params.set('email', email)
  if (purpose) params.set('purpose', purpose)
  const query = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`/api/demo/outbox${query}`)
  if (!res.ok) {
    throw new Error(`获取信箱失败: ${res.statusText}`)
  }
  return res.json()
}

// Admin APIs (Bearer token authenticated)
function getAdminHeaders(): HeadersInit {
  const token = tokenStore.getAccessToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export async function adminGetUsers(): Promise<AdminUserItem[]> {
  const res = await fetch('/api/admin/account/users', {
    headers: getAdminHeaders(),
  })
  const data = await res.json()
  if (!res.ok) {
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '获取用户列表失败'
        : data.detail || '获取用户列表失败'
    throw new Error(msg)
  }
  return data
}

export async function adminPatchUser(
  userId: string,
  patch: {
    role?: string
    is_admin?: boolean
    is_active?: boolean
    approval_status?: 'pending' | 'approved' | 'rejected'
    tier_code?: string
  }
): Promise<AdminUserItem> {
  const res = await fetch(`/api/admin/account/users/${userId}`, {
    method: 'PATCH',
    headers: getAdminHeaders(),
    body: JSON.stringify(patch),
  })
  const data = await res.json()
  if (!res.ok) {
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '更新用户失败'
        : data.detail || '更新用户失败'
    throw new Error(msg)
  }
  return data
}

export async function adminDeleteUser(userId: string): Promise<void> {
  const res = await fetch(`/api/admin/account/users/${userId}`, {
    method: 'DELETE',
    headers: getAdminHeaders(),
  })
  if (!res.ok && res.status !== 204) {
    const data = await res.json().catch(() => ({}))
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '删除用户失败'
        : data.detail || '删除用户失败'
    throw new Error(msg)
  }
}

export async function adminReset2Fa(userId: string): Promise<void> {
  const res = await fetch(`/api/admin/account/users/${userId}/2fa/reset`, {
    method: 'POST',
    headers: getAdminHeaders(),
  })
  if (!res.ok && res.status !== 204) {
    const data = await res.json().catch(() => ({}))
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '重置 2FA 失败'
        : data.detail || '重置 2FA 失败'
    throw new Error(msg)
  }
}

export async function adminGetAuditLogs(params: {
  page?: number
  page_size?: number
  user_id?: string
  event?: string
  ip?: string
  since?: string
  until?: string
}): Promise<AuditLogsResponse> {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.user_id) search.set('user_id', params.user_id)
  if (params.event) search.set('event', params.event)
  if (params.ip) search.set('ip', params.ip)
  if (params.since) search.set('since', params.since)
  if (params.until) search.set('until', params.until)

  const query = search.toString() ? `?${search.toString()}` : ''
  const res = await fetch(`/api/admin/account/audit-logs${query}`, {
    headers: getAdminHeaders(),
  })
  const data = await res.json()
  if (!res.ok) {
    const msg =
      typeof data.detail === 'object'
        ? data.detail?.message || data.detail?.code || '获取审计日志失败'
        : data.detail || '获取审计日志失败'
    throw new Error(msg)
  }
  return data
}
