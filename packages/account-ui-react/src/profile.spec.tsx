import { cleanup, fireEvent, render, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { type AccountClient, type AccountUser } from "./client"
import { ProfileFields } from "./profile"

const baseUser = {
  id: "u1",
  username: "sso",
  email: "sso@example.com",
  role: "user",
  is_admin: false,
  is_active: true,
  approval_status: "approved",
} as AccountUser

function mockClient() {
  return {
    patchMe: vi.fn().mockResolvedValue({}),
    changePassword: vi.fn().mockResolvedValue({ status: "success" }),
    sendCode: vi.fn().mockResolvedValue({ status: "success" }),
  }
}

describe("ProfileFields password_set", () => {
  afterEach(() => cleanup())

  it("password_set=false shows Set password, hides old password, requires email code", async () => {
    const client = mockClient()
    render(<ProfileFields client={client as unknown as AccountClient} token="t" user={{ ...baseUser, password_set: false }} language="zh-CN" />)
    expect(document.querySelector("h3")?.textContent).toBe("设置密码")
    expect(document.querySelector('input[autocomplete="current-password"]')).toBeNull()
    const code = document.querySelector('input[autocomplete="one-time-code"]') as HTMLInputElement
    expect(code).not.toBeNull()
    const send = Array.from(document.querySelectorAll("button")).find((b) => b.textContent === "发送验证码")!
    fireEvent.click(send)
    await waitFor(() => expect(client.sendCode).toHaveBeenCalledWith("sso@example.com", "change_password", "zh-CN", "t"))
    const pw = document.querySelectorAll('input[autocomplete="new-password"]')
    fireEvent.change(pw[0], { target: { value: "secret2" } })
    fireEvent.change(pw[1], { target: { value: "secret2" } })
    fireEvent.change(code, { target: { value: "123456" } })
    fireEvent.submit(document.querySelector("form") as HTMLFormElement)
    await waitFor(() => expect(client.changePassword).toHaveBeenCalledWith("t", "", "secret2", "123456"))
  })

  it("English label is pure English", () => {
    render(<ProfileFields client={mockClient() as unknown as AccountClient} token="t" user={{ ...baseUser, password_set: false }} language="en" />)
    expect(document.querySelector("h3")?.textContent).toBe("Set password")
  })

  it("password_set true/absent keeps Change password with old password", () => {
    render(<ProfileFields client={mockClient() as unknown as AccountClient} token="t" user={baseUser} language="zh-CN" />)
    expect(document.querySelector("h3")?.textContent).toBe("修改密码")
    expect(document.querySelector('input[autocomplete="current-password"]')).not.toBeNull()
    expect(document.querySelector('input[autocomplete="one-time-code"]')).toBeNull()
  })
})
