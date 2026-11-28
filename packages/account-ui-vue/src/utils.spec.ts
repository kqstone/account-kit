import { describe, expect, it } from "vitest"
import { AccountApiError } from "./client"
import { canonicalErrorCode, formatError } from "./utils"

function err(code: string, extra: Record<string, unknown> = {}, status = 403) {
  const detail = { code, message: code, ...extra }
  return new AccountApiError(code, status, { detail, code, params: extra })
}

describe("formatError approval / SSO codes", () => {
  it("maps USER_PENDING to ACCOUNT_PENDING copy", () => {
    expect(formatError(err("USER_PENDING"))).toBe("账号尚未通过审批")
    expect(canonicalErrorCode("USER_PENDING")).toBe("ACCOUNT_PENDING")
  })

  it("maps USER_REJECTED to ACCOUNT_REJECTED copy", () => {
    expect(formatError(err("USER_REJECTED"))).toBe("账号未通过审核")
    expect(canonicalErrorCode("USER_REJECTED")).toBe("ACCOUNT_REJECTED")
  })

  it("shows rejection reason when params.reason is set", () => {
    expect(formatError(err("ACCOUNT_REJECTED", { reason: "材料不全" }))).toBe("账号未通过审核：材料不全")
    expect(formatError(err("USER_REJECTED", { reason: "材料不全" }))).toBe("账号未通过审核：材料不全")
  })

  it("keeps English catalogs free of CJK for bind-ticket expiry", () => {
    const text = formatError(err("SSO_BIND_TICKET_EXPIRED", {}, 400), null, "en")
    expect(text).toBe("Bind ticket expired, please sign in with the identity provider again")
    expect(/[\u4e00-\u9fff]/.test(text)).toBe(false)
  })

  it("maps send-code codes including PASSWORD_RESET_NOT_ALLOWED", () => {
    expect(formatError(err("EMAIL_TAKEN", {}, 400))).toBe("该邮箱已注册")
    expect(formatError(err("EMAIL_NOT_REGISTERED", {}, 404))).toBe("该邮箱未注册账号")
    expect(formatError(err("EMAIL_INVALID", {}, 400))).toBe("邮箱无效")
    expect(formatError(err("PASSWORD_RESET_NOT_ALLOWED", {}, 400))).toBe("该账号不支持通过此方式重置密码")
    expect(formatError(err("PASSWORD_RESET_NOT_ALLOWED", {}, 400), null, "en")).toBe(
      "This account does not support resetting the password this way",
    )
  })
})

describe("send-code helpers", () => {
  it("isSimpleEmail requires @ and a dotted domain", async () => {
    const { isSimpleEmail, cooldownFromResult, retryAfterFromError, DEFAULT_SEND_CODE_COOLDOWN } = await import("./utils")
    expect(isSimpleEmail("")).toBe(false)
    expect(isSimpleEmail("foo")).toBe(false)
    expect(isSimpleEmail("a@b")).toBe(false)
    expect(isSimpleEmail("a@b.com")).toBe(true)
    expect(cooldownFromResult(undefined)).toBe(DEFAULT_SEND_CODE_COOLDOWN)
    expect(cooldownFromResult({ cooldown: 90 })).toBe(90)
    expect(retryAfterFromError(err("EMAIL_CODE_TOO_FREQUENT", { retry_after: 45 }, 429))).toBe(45)
    expect(retryAfterFromError(err("RATE_LIMITED", {}, 429))).toBe(120)
  })
})
