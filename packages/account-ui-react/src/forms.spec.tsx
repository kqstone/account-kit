import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AccountApiError, type AccountClient } from "./client"
import { LoginForm, RegisterForm, ResetPasswordForm } from "./forms"

function apiError(code: string, status = 400, extra: Record<string, unknown> = {}) {
  return new AccountApiError(code, status, { detail: { code, message: code, ...extra }, code })
}

function mockClient() {
  return {
    login: vi.fn().mockResolvedValue({ access_token: "tok", token_type: "bearer" }),
  }
}

describe("LoginForm remember-login", () => {
  afterEach(() => {
    cleanup()
    document.body.innerHTML = ""
  })

  it("prefills defaultUsername/defaultPassword and sets name/autocomplete", () => {
    const client = mockClient()
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="alice"
        defaultPassword="secret1"
        onSuccess={() => undefined}
      />,
    )
    const user = document.querySelector('input[name="username"]') as HTMLInputElement
    const pass = document.querySelector('input[name="password"]') as HTMLInputElement
    expect(user.autocomplete).toBe("username")
    expect(pass.autocomplete).toBe("current-password")
    expect(user.value).toBe("alice")
    expect(pass.value).toBe("secret1")
  })

  it("beforeSubmit false aborts login; async false too", async () => {
    const client = mockClient()
    const before = vi.fn().mockReturnValue(false)
    const { unmount } = render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="carol"
        defaultPassword="secret1"
        beforeSubmit={before}
        onSuccess={() => undefined}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(before).toHaveBeenCalled())
    expect(before).toHaveBeenCalledWith({ username: "carol", password: "secret1" })
    expect(client.login).not.toHaveBeenCalled()
    unmount()

    const asyncFalse = vi.fn().mockResolvedValue(false)
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="carol"
        defaultPassword="secret1"
        beforeSubmit={asyncFalse}
        onSuccess={() => undefined}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(asyncFalse).toHaveBeenCalled())
    expect(client.login).not.toHaveBeenCalled()
  })

  it("onSuccess receives credentials as the second argument", async () => {
    const client = mockClient()
    const onSuccess = vi.fn()
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="dave"
        defaultPassword="secret1"
        onSuccess={onSuccess}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(onSuccess.mock.calls[0][0]).toBe("tok")
    expect(onSuccess.mock.calls[0][1]).toMatchObject({ username: "dave", password: "secret1" })
  })
})

describe("RegisterForm pending", () => {
  afterEach(() => {
    cleanup()
    document.body.innerHTML = ""
  })

  it("shows registerPending when the created user is pending", async () => {
    const client = {
      roles: vi.fn().mockResolvedValue([]),
      register: vi.fn().mockResolvedValue({ username: "ada", approval_status: "pending" }),
      sendCode: vi.fn(),
    }
    const onSuccess = vi.fn()
    render(<RegisterForm client={client as unknown as AccountClient} onSuccess={onSuccess} />)
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(screen.getByText("注册成功，账号待管理员审批后方可登录")).toBeTruthy()
  })

  it("does not show pending copy for an approved user", async () => {
    const client = {
      roles: vi.fn().mockResolvedValue([]),
      register: vi.fn().mockResolvedValue({ username: "ada", approval_status: "approved" }),
      sendCode: vi.fn(),
    }
    render(<RegisterForm client={client as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(client.register).toHaveBeenCalled())
    expect(screen.queryByText("注册成功，账号待管理员审批后方可登录")).toBeNull()
  })
})

describe("RegisterForm / ResetPasswordForm send-code UX", () => {
  afterEach(() => {
    cleanup()
    document.body.innerHTML = ""
  })

  function registerClient(sendCode: ReturnType<typeof vi.fn>) {
    return {
      roles: vi.fn().mockResolvedValue([]),
      register: vi.fn(),
      sendCode,
    }
  }

  it("does not send when email is empty or invalid", async () => {
    const sendCode = vi.fn()
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    const btn = document.querySelector("button.ak-code-btn") as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(sendCode).not.toHaveBeenCalled()
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "not-an-email" } })
    expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    expect(sendCode).not.toHaveBeenCalled()
  })

  it("shows sending lock then success countdown from cooldown (default 120)", async () => {
    let finish!: (value: unknown) => void
    const sendCode = vi.fn().mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "ada@example.com" } })
    const btn = document.querySelector("button.ak-code-btn") as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    await waitFor(() => expect(btn.textContent).toBe("发送中…"))
    expect(btn.disabled).toBe(true)
    expect(sendCode).toHaveBeenCalledTimes(1)
    finish({ status: "ok", cooldown: 90, email: "ada@example.com" })
    await waitFor(() => expect(document.body.textContent).toContain("验证码已发送至 ada@example.com"))
    expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("90 秒后重发")
    expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).disabled).toBe(true)
  })

  it("falls back to 120s when cooldown is missing", async () => {
    const sendCode = vi.fn().mockResolvedValue({ status: "ok" })
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "ada@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("120 秒后重发"))
  })

  it("EMAIL_TAKEN shows copy and hint without countdown", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_TAKEN"))
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "ada@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect(document.body.textContent).toContain("该邮箱已注册"))
    expect(document.body.textContent).toContain("请直接登录或找回密码")
    expect(document.body.textContent).not.toContain("秒后重发")
    expect(document.body.textContent).not.toContain("验证码已发送")
    expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("发送验证码")
  })

  it("EMAIL_NOT_REGISTERED and PASSWORD_RESET_NOT_ALLOWED show copy without countdown", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_NOT_REGISTERED", 404))
    const { unmount } = render(
      <ResetPasswordForm client={{ sendCode, resetPassword: vi.fn() } as unknown as AccountClient} onSuccess={() => undefined} />,
    )
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "nobody@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect(document.body.textContent).toContain("该邮箱未注册账号"))
    expect(document.body.textContent).not.toContain("秒后重发")
    expect(document.body.textContent).not.toContain("验证码已发送")
    unmount()

    sendCode.mockRejectedValueOnce(apiError("PASSWORD_RESET_NOT_ALLOWED"))
    render(<ResetPasswordForm client={{ sendCode, resetPassword: vi.fn() } as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "admin@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect(document.body.textContent).toContain("该账号不支持通过此方式重置密码"))
    expect(document.body.textContent).not.toMatch(/管理员/)
    expect(document.body.textContent).not.toContain("秒后重发")
  })

  it("rate-limit errors use retry_after and fall back to 120", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_CODE_TOO_FREQUENT", 429, { retry_after: 45 }))
    const { unmount } = render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "ada@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("45 秒后重发"))
    expect(document.body.textContent).toContain("验证码发送频繁")
    expect(document.body.textContent).not.toContain("验证码已发送")
    unmount()

    sendCode.mockRejectedValueOnce(apiError("RATE_LIMITED", 429))
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "ada@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("120 秒后重发"))
    expect(document.body.textContent).not.toContain("验证码已发送")
  })

  it("allows sending to a new address after a successful send", async () => {
    const sendCode = vi.fn().mockResolvedValue({ status: "ok", cooldown: 120 })
    render(<RegisterForm client={registerClient(sendCode) as unknown as AccountClient} onSuccess={() => undefined} />)
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "old@example.com" } })
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).disabled).toBe(true))
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLInputElement, { target: { value: "new@example.com" } })
    await waitFor(() => expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).disabled).toBe(false))
    expect((document.querySelector("button.ak-code-btn") as HTMLButtonElement).textContent).toBe("发送验证码")
    fireEvent.click(document.querySelector("button.ak-code-btn") as HTMLButtonElement)
    await waitFor(() => expect(sendCode).toHaveBeenCalledTimes(2))
    expect(sendCode).toHaveBeenNthCalledWith(2, "new@example.com", "register", "zh-CN")
  })
})
