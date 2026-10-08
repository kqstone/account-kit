import { AccountApiError } from "./client"
import { defaultErrorLabels } from "./errors"

export type KitLocale = "zh-CN" | "en"

export function interpolate(template: string, params?: Record<string, string | number | undefined>) {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params[key]
    return value == null ? `{${key}}` : String(value)
  })
}

export function resolveLocale(language?: string | null): KitLocale {
  const text = String(language || "zh-CN").trim().replace(/_/g, "-")
  const low = text.toLowerCase()
  if (low === "en" || low.startsWith("en-")) return "en"
  return "zh-CN"
}

export function messageOf(error: unknown, fallback?: string) {
  const text = fallback ?? defaultErrorLabels[resolveLocale()].REQUEST_FAILED
  if (error instanceof AccountApiError) return error.message || text
  if (error instanceof Error) return error.message
  return text
}

export function errorCodeOf(error: unknown): string | undefined {
  return error instanceof AccountApiError ? error.code : undefined
}

export function errorParamsOf(error: unknown): Record<string, string | number> {
  if (!(error instanceof AccountApiError) || !error.body || typeof error.body !== "object") return {}
  const body = error.body as { params?: unknown; detail?: unknown }
  const out: Record<string, string | number> = {}
  if (body.params && typeof body.params === "object") {
    for (const [key, value] of Object.entries(body.params as Record<string, unknown>)) {
      if (typeof value === "string" || typeof value === "number") out[key] = value
    }
  }
  const detail = body.detail
  if (detail && typeof detail === "object") {
    for (const key of ["attempts_left", "retry_after", "device_name", "allowed"]) {
      const value = (detail as Record<string, unknown>)[key]
      if (typeof value === "string" || typeof value === "number") out[key] = value
    }
  }
  return out
}

export function formatError(
  error: unknown,
  labels?: { errors?: Record<string, string>; error?: string } | null,
  locale?: string,
): string {
  const loc = resolveLocale(locale)
  const fallback = labels?.error || labels?.errors?.REQUEST_FAILED || defaultErrorLabels[loc].REQUEST_FAILED
  const code = errorCodeOf(error)
  const table: Record<string, string> = { ...defaultErrorLabels[loc], ...(labels?.errors || {}) }
  if (code && table[code]) return interpolate(table[code], errorParamsOf(error))
  return messageOf(error, fallback)
}

export function textOf(event: Event) {
  return (event.target as HTMLInputElement).value
}

export function formatDateTime(iso?: string | null, locale?: string) {
  if (!iso) return "—"
  const stamped = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`
  const date = new Date(stamped)
  const tag = resolveLocale(locale) === "en" ? "en" : "zh-CN"
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(tag)
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
