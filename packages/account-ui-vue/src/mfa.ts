import { AccountApiError } from "./client"
import { defaultTwoFactorLabels, type TwoFactorLabels } from "./labels"
import { interpolate, resolveLocale } from "./utils"

export const MFA_REQUIRED = "MFA_REQUIRED"
export const FACTOR_TOTP = "totp"
export const FACTOR_RECOVERY = "recovery"
export const FACTOR_EMAIL = "email"
export type SecondFactor = typeof FACTOR_TOTP | typeof FACTOR_RECOVERY | typeof FACTOR_EMAIL

export type MfaChallenge = {
  challengeToken: string
  emailAvailable: boolean
  expiresIn: number
  trustedDays: number
  methods?: string[]
}

export type FactorInputs = { code?: string; recoveryCode?: string; emailCode?: string }

export function errorDetail(error: unknown): Record<string, unknown> | string | null {
  if (error instanceof AccountApiError && error.body && typeof error.body === "object" && "detail" in error.body) {
    return (error.body as { detail: Record<string, unknown> | string }).detail
  }
  return null
}

export function errorCodeOf(error: unknown): string | null {
  if (error instanceof AccountApiError && error.code) return error.code
  const detail = errorDetail(error)
  return detail && typeof detail === "object" && typeof detail.code === "string" ? detail.code : null
}

export function getMfaChallenge(error: unknown): MfaChallenge | null {
  const detail = errorDetail(error)
  const status = error instanceof AccountApiError ? error.status : 0
  if (status !== 401 || !detail || typeof detail !== "object" || detail.code !== MFA_REQUIRED) return null
  const token = detail.challenge_token || detail.challengeToken
  if (!token) return null
  return {
    challengeToken: String(token),
    emailAvailable: !!(detail.email_available ?? detail.emailAvailable),
    expiresIn: Number(detail.expires_in ?? detail.expiresIn) || 300,
    trustedDays: Number(detail.trusted_device_days ?? detail.trustedDays) || 30,
    methods: Array.isArray(detail.methods) ? (detail.methods as string[]) : undefined,
  }
}

export function normalizeChallenge(raw: Record<string, unknown> | MfaChallenge | null | undefined): MfaChallenge | null {
  if (!raw || typeof raw !== "object") return null
  const token = (raw as MfaChallenge).challengeToken || (raw as { challenge_token?: unknown }).challenge_token
  if (!token) return null
  const rec = raw as Record<string, unknown>
  return {
    challengeToken: String(token),
    emailAvailable: !!(rec.emailAvailable ?? rec.email_available),
    expiresIn: Number(rec.expiresIn ?? rec.expires_in) || 300,
    trustedDays: Number(rec.trustedDays ?? rec.trusted_device_days) || 30,
    methods: Array.isArray(rec.methods) ? (rec.methods as string[]) : undefined,
  }
}

export function secondFactorFields(factor: SecondFactor, inputs: FactorInputs = {}) {
  const out = { code: "", recoveryCode: "", emailCode: "" }
  if (factor === FACTOR_RECOVERY) out.recoveryCode = normalizeRecoveryInput(inputs.recoveryCode)
  else if (factor === FACTOR_EMAIL) out.emailCode = normalizeTotpInput(inputs.emailCode)
  else out.code = normalizeTotpInput(inputs.code)
  return out
}

export function canSubmitFactor(factor: SecondFactor, inputs: FactorInputs = {}) {
  const fields = secondFactorFields(factor, inputs)
  if (factor === FACTOR_RECOVERY) return fields.recoveryCode.replace(/-/g, "").length >= 8
  if (factor === FACTOR_EMAIL) return fields.emailCode.length === 6
  return fields.code.length === 6
}

export function normalizeTotpInput(value?: string | null) {
  return String(value || "")
    .replace(/\D/g, "")
    .slice(0, 6)
}

export function normalizeRecoveryInput(value?: string | null) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "")
    .slice(0, 16)
}

export function formatSecret(secret?: string | null) {
  return String(secret || "")
    .replace(/\s+/g, "")
    .replace(/(.{4})/g, "$1 ")
    .trim()
}

export function recoveryCodesText(
  codes: string[],
  {
    username = "",
    brand = "account-kit",
    generatedAt = new Date(),
    locale,
    labels,
  }: {
    username?: string
    brand?: string
    generatedAt?: Date
    locale?: string
    labels?: Pick<TwoFactorLabels, "recoveryFileTitle" | "recoveryFileAccount" | "recoveryFileGenerated" | "recoveryFileOnce">
  } = {},
) {
  const L = { ...defaultTwoFactorLabels[resolveLocale(locale)], ...labels }
  return [
    interpolate(L.recoveryFileTitle, { brand }),
    username ? interpolate(L.recoveryFileAccount, { username }) : null,
    interpolate(L.recoveryFileGenerated, { time: generatedAt.toISOString() }),
    L.recoveryFileOnce,
    "",
    ...codes,
    "",
  ]
    .filter((line) => line !== null)
    .join("\n")
}

const KNOWN_ERRORS = new Set([
  "PASSWORD_INCORRECT",
  "MFA_CODE_REQUIRED",
  "MFA_CODE_INVALID",
  "MFA_CHALLENGE_INVALID",
  "MFA_TOO_MANY_ATTEMPTS",
  "MFA_ALREADY_VERIFIED",
  "RATE_LIMITED",
  "TWO_FACTOR_ALREADY_ENABLED",
  "TWO_FACTOR_NOT_ENABLED",
  "TWO_FACTOR_SETUP_REQUIRED",
  "TWO_FACTOR_SETUP_EXPIRED",
  "TWO_FACTOR_CODE_INVALID",
  "EMAIL_UNAVAILABLE",
  "EMAIL_CODE_INVALID",
  "EMAIL_CODE_TOO_FREQUENT",
  "DEVICE_NOT_FOUND",
])

export function describeTwoFactorError(error: unknown) {
  const status = error instanceof AccountApiError ? error.status : 0
  const detail = errorDetail(error)
  let code = error instanceof AccountApiError ? error.code || null : null
  if (!code && detail && typeof detail === "object" && typeof detail.code === "string") code = detail.code
  if (!code && status === 429) code = "RATE_LIMITED"
  const fallback =
    (detail && typeof detail === "object" && typeof detail.message === "string" && detail.message) ||
    (typeof detail === "string" ? detail : "") ||
    (error instanceof Error ? error.message : "")
  const params: Record<string, string | number | undefined> = {}
  if (detail && typeof detail === "object" && typeof detail.attempts_left === "number") params.left = detail.attempts_left
  return { key: code && KNOWN_ERRORS.has(code) ? code : null, params, fallback, code }
}

export function twoFactorErrorMessage(error: unknown, labels: TwoFactorLabels) {
  const described = describeTwoFactorError(error)
  if (described.key && labels.errors[described.key]) return interpolate(labels.errors[described.key], described.params)
  return described.fallback || labels.error
}
