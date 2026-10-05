import { AccountApiError } from "./client"

export function messageOf(error: unknown, fallback = "请求失败") {
  if (error instanceof AccountApiError) return error.message || fallback
  if (error instanceof Error) return error.message
  return fallback
}

export function textOf(event: Event) {
  return (event.target as HTMLInputElement).value
}

export function interpolate(template: string, params?: Record<string, string | number | undefined>) {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params[key]
    return value == null ? `{${key}}` : String(value)
  })
}

export function resolveLocale(language?: string): "zh" | "en" {
  return String(language || "zh").toLowerCase().startsWith("en") ? "en" : "zh"
}

export function formatDateTime(iso?: string | null) {
  if (!iso) return "—"
  const stamped = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`
  const date = new Date(stamped)
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString()
}

export function initialsOf(user?: { full_name?: string | null; username?: string | null } | null) {
  const name = (user?.full_name || user?.username || "").trim()
  return name ? name.slice(0, 1).toUpperCase() : "?"
}

export type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value)
}

export function mergeLabels<T extends object>(base: T, override?: DeepPartial<T> | null): T {
  if (!override) return base
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) }
  for (const key of Object.keys(override)) {
    const next = (override as Record<string, unknown>)[key]
    const prev = out[key]
    if (isRecord(prev) && isRecord(next)) out[key] = mergeLabels(prev, next)
    else if (next !== undefined) out[key] = next
  }
  return out as T
}
