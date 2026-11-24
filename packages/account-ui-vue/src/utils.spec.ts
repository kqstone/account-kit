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
})
