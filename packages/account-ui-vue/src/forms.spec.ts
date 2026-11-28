import { flushPromises, mount } from "@vue/test-utils"
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
    document.body.innerHTML = ""
  })

  it("prefills defaultUsername/defaultPassword and keeps initialUsername alias", async () => {
    const client = mockClient()
    const wrapper = mount(LoginForm, {
      props: {
        client: client as unknown as AccountClient,
        defaultUsername: "alice",
        defaultPassword: "secret1",
      },
    })
    const user = wrapper.find('input[name="username"]')
    const pass = wrapper.find('input[name="password"]')
    expect(user.attributes("autocomplete")).toBe("username")
    expect(pass.attributes("autocomplete")).toBe("current-password")
    expect((user.element as HTMLInputElement).value).toBe("alice")
    expect((pass.element as HTMLInputElement).value).toBe("secret1")
    wrapper.unmount()

    const alias = mount(LoginForm, {
      props: {
        client: client as unknown as AccountClient,
        initialUsername: "bob",
        initialPassword: "oldpw",
      },
    })
    expect((alias.find('input[name="username"]').element as HTMLInputElement).value).toBe("bob")
    alias.unmount()
  })

  it("beforeSubmit false aborts login; async false too", async () => {
    const client = mockClient()
    const before = vi.fn().mockReturnValue(false)
    const wrapper = mount(LoginForm, {
      props: {
        client: client as unknown as AccountClient,
        defaultUsername: "carol",
        defaultPassword: "secret1",
        beforeSubmit: before,
      },
    })
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(before).toHaveBeenCalledWith({ username: "carol", password: "secret1" })
    expect(client.login).not.toHaveBeenCalled()
    wrapper.unmount()

    const asyncFalse = vi.fn().mockResolvedValue(false)
    const again = mount(LoginForm, {
      props: {
        client: client as unknown as AccountClient,
        defaultUsername: "carol",
        defaultPassword: "secret1",
        beforeSubmit: asyncFalse,
      },
    })
    await again.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(client.login).not.toHaveBeenCalled()
    again.unmount()
  })

  it("emits success with credentials after login", async () => {
    const client = mockClient()
    const wrapper = mount(LoginForm, {
      props: {
        client: client as unknown as AccountClient,
        defaultUsername: "dave",
        defaultPassword: "secret1",
      },
    })
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(client.login).toHaveBeenCalled()
    const emitted = wrapper.emitted("success")
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe("tok")
    expect(emitted![0][1]).toMatchObject({ username: "dave", password: "secret1" })
    wrapper.unmount()
  })
})

describe("RegisterForm pending", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("shows registerPending when the created user is pending", async () => {
    const client = {
      roles: vi.fn().mockResolvedValue([]),
      register: vi.fn().mockResolvedValue({ username: "ada", approval_status: "pending" }),
      sendCode: vi.fn(),
    }
    const wrapper = mount(RegisterForm, {
      props: { client: client as unknown as AccountClient },
    })
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(wrapper.text()).toContain("注册成功，账号待管理员审批后方可登录")
    wrapper.unmount()
  })

  it("does not show pending copy for an approved user", async () => {
    const client = {
      roles: vi.fn().mockResolvedValue([]),
      register: vi.fn().mockResolvedValue({ username: "ada", approval_status: "approved" }),
      sendCode: vi.fn(),
    }
    const wrapper = mount(RegisterForm, {
      props: { client: client as unknown as AccountClient },
    })
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(wrapper.text()).not.toContain("注册成功，账号待管理员审批后方可登录")
    wrapper.unmount()
  })
})

describe("RegisterForm / ResetPasswordForm send-code UX", () => {
  afterEach(() => {
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
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    const btn = wrapper.find("button.ak-code-btn")
    expect(btn.attributes("disabled")).toBeDefined()
    await btn.trigger("click")
    await flushPromises()
    expect(sendCode).not.toHaveBeenCalled()
    await wrapper.find('input[type="email"]').setValue("not-an-email")
    expect(wrapper.find("button.ak-code-btn").attributes("disabled")).toBeDefined()
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(sendCode).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("shows sending lock then success countdown from cooldown (default 120)", async () => {
    let finish!: (value: unknown) => void
    const sendCode = vi.fn().mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("ada@example.com")
    const btn = wrapper.find("button.ak-code-btn")
    expect(btn.attributes("disabled")).toBeUndefined()
    await btn.trigger("click")
    await flushPromises()
    expect(btn.text()).toBe("发送中…")
    expect(btn.attributes("disabled")).toBeDefined()
    expect(sendCode).toHaveBeenCalledTimes(1)
    finish({ status: "ok", cooldown: 90, email: "ada@example.com" })
    await flushPromises()
    expect(wrapper.text()).toContain("验证码已发送至 ada@example.com")
    expect(wrapper.find("button.ak-code-btn").text()).toBe("90 秒后重发")
    expect(wrapper.find("button.ak-code-btn").attributes("disabled")).toBeDefined()
    wrapper.unmount()
  })

  it("falls back to 120s when cooldown is missing", async () => {
    const sendCode = vi.fn().mockResolvedValue({ status: "ok" })
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("ada@example.com")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(wrapper.find("button.ak-code-btn").text()).toBe("120 秒后重发")
    wrapper.unmount()
  })

  it("EMAIL_TAKEN shows copy and hint without countdown", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_TAKEN"))
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("ada@example.com")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain("该邮箱已注册")
    expect(wrapper.text()).toContain("请直接登录或找回密码")
    expect(wrapper.text()).not.toContain("秒后重发")
    expect(wrapper.text()).not.toContain("验证码已发送")
    expect(wrapper.find("button.ak-code-btn").text()).toBe("发送验证码")
    wrapper.unmount()
  })

  it("EMAIL_NOT_REGISTERED and PASSWORD_RESET_NOT_ALLOWED show copy without countdown", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_NOT_REGISTERED", 404))
    const wrapper = mount(ResetPasswordForm, { props: { client: { sendCode, resetPassword: vi.fn() } as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("nobody@example.com")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain("该邮箱未注册账号")
    expect(wrapper.text()).not.toContain("秒后重发")
    expect(wrapper.text()).not.toContain("验证码已发送")
    wrapper.unmount()

    sendCode.mockRejectedValueOnce(apiError("PASSWORD_RESET_NOT_ALLOWED"))
    const again = mount(ResetPasswordForm, { props: { client: { sendCode, resetPassword: vi.fn() } as unknown as AccountClient } })
    await again.find('input[type="email"]').setValue("admin@example.com")
    await again.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(again.text()).toContain("该账号不支持通过此方式重置密码")
    expect(again.text()).not.toMatch(/管理员/)
    expect(again.text()).not.toContain("秒后重发")
    again.unmount()
  })

  it("rate-limit errors use retry_after and fall back to 120", async () => {
    const sendCode = vi.fn().mockRejectedValue(apiError("EMAIL_CODE_TOO_FREQUENT", 429, { retry_after: 45 }))
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("ada@example.com")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain("验证码发送频繁")
    expect(wrapper.text()).not.toContain("验证码已发送")
    expect(wrapper.find("button.ak-code-btn").text()).toBe("45 秒后重发")
    wrapper.unmount()

    sendCode.mockRejectedValueOnce(apiError("RATE_LIMITED", 429))
    const again = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await again.find('input[type="email"]').setValue("ada@example.com")
    await again.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(again.find("button.ak-code-btn").text()).toBe("120 秒后重发")
    expect(again.text()).not.toContain("验证码已发送")
    again.unmount()
  })

  it("allows sending to a new address after a successful send", async () => {
    const sendCode = vi.fn().mockResolvedValue({ status: "ok", cooldown: 120 })
    const wrapper = mount(RegisterForm, { props: { client: registerClient(sendCode) as unknown as AccountClient } })
    await wrapper.find('input[type="email"]').setValue("old@example.com")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(wrapper.find("button.ak-code-btn").attributes("disabled")).toBeDefined()
    await wrapper.find('input[type="email"]').setValue("new@example.com")
    expect(wrapper.find("button.ak-code-btn").attributes("disabled")).toBeUndefined()
    expect(wrapper.find("button.ak-code-btn").text()).toBe("发送验证码")
    await wrapper.find("button.ak-code-btn").trigger("click")
    await flushPromises()
    expect(sendCode).toHaveBeenNthCalledWith(2, "new@example.com", "register", "zh-CN")
    wrapper.unmount()
  })
})
