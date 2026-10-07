export interface SetupFeatures {
  refresh?: boolean
  captcha?: boolean
  self_delete?: boolean
  two_factor_email?: boolean
  require_approval?: boolean
  two_factor?: boolean
  logout?: boolean
  audit_log?: boolean
  role_change?: boolean
  session_mode?: string
  captcha_fail_threshold?: number
  [key: string]: unknown
}

export interface SetupStatusResponse {
  initialized: boolean
  features: SetupFeatures | null
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

export interface OutboxResponse {
  items: OutboxItem[]
}

export interface AdminUserItem {
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
  approval_status: 'pending' | 'approved' | 'rejected' | string
  has_custom_avatar?: boolean
  pending_role?: string | null
  tier?: string | null
  tier_name?: string | null
  tier_badge_color?: string | null
}

export interface AuditLogItem {
  id: string
  user_id: string | null
  event: string
  ip?: string | null
  device_name?: string | null
  meta?: Record<string, unknown> | null
  created_at: string
}

export interface AuditLogsResponse {
  items: AuditLogItem[]
  total: number
  page: number
  page_size: number
}
