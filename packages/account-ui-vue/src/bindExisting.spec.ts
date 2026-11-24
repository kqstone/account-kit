import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import { BindExistingAccountForm } from "./bindExisting"
import { AccountApiError, type AccountClient, type BindExistingPayload, type TokenPair } from "./client"

function apiError(status: number, code: string, extra: Record<string, unknown> = {}) {
  const detail = { code, message: code, ...extra }
  return new AccountApiError(code, status, { detail, code, params: extra })
}

function mockClient() {
  return {
    captcha: vi.fn(async () => ({ captcha_id: "cid-1", image_base64: "img1", expires_in: 300 })),
    loginSecondFactor: vi.fn(),
    sendLoginEmailCode: vi.fn(async () => ({ email: "a***@ex.com", cooldown: 60 })),
  }
}

async function fillAndSubmit(wrapper: VueWrapper, username = "carol", password = "secret1") {
  await wrapper.find('input[autocomplete="username"]').setValue(username)
  await wrapper.find('input[autocomplete="current-password"]').setValue(password)
  await wrapper.find("form.ak-form").trigger("submit")
  await flushPromises()
}

describe("BindExistingAccountForm", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("accepts username or email and posts the same payload", async () => {
    const client = mockClient()
    const bindExisting = vi.fn(async (payload: BindExistingPayload) => {
      expect(payload.username).toBe("ada@example.com")
      expect(payload.password).toBe("secret1")
      expect(payload.bindTicket).toBe("tk-1")
      return { access_token: "tok", token_type: "bearer" } as TokenPair
    })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        allowReclaim: true,
      },
    })
    expect(wrapper.text()).toContain("用户名或邮箱")
    await fillAndSubmit(wrapper, "ada@example.com")
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it("shows captcha then retries with captcha fields", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(apiError(428, "CAPTCHA_REQUIRED", { captcha_required: true }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
      },
    })
    await fillAndSubmit(wrapper)
    expect(wrapper.find('input[placeholder="输入图中字符"]').exists()).toBe(true)
    await wrapper.find('input[placeholder="输入图中字符"]').setValue("ABCD")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(bindExisting).toHaveBeenCalledTimes(2)
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      captchaId: "cid-1",
      captchaCode: "ABCD",
      bindTicket: "tk-1",
    })
    wrapper.unmount()
  })

  it("asks for reclaim confirm then resubmits with reclaim true", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(apiError(409, "SSO_ORPHAN_PENDING", { orphan_username: "ghost" }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        allowReclaim: true,
      },
    })
    await fillAndSubmit(wrapper, "olduser")
    expect(wrapper.text()).toContain("待审空号 ghost")
    expect(wrapper.find("form.ak-form button").text()).toBe("确认改绑")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting.mock.calls[1][0]).toMatchObject({ reclaim: true, username: "olduser", bindTicket: "tk-1" })
    wrapper.unmount()
  })

  it("SSO MFA re-POSTs bind-existing with the same ticket, not login/2fa", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", {
          challenge_token: "ch-1",
          bind_ticket: "tk-1",
          email_available: true,
          expires_in: 300,
        }),
      )
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        completeMfaViaLogin2fa: false,
      },
    })
    await fillAndSubmit(wrapper)
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.findAll("button").find((b) => b.text() === "跳过两步验证（发送邮箱验证码登录）")!.trigger("click")
    await flushPromises()
    expect(client.sendLoginEmailCode).toHaveBeenCalledWith("ch-1", "zh-CN")
    await wrapper.findAll("button").find((b) => b.text() === "使用验证器验证码")!.trigger("click")
    await wrapper.find('input[placeholder="000000"]').setValue("123456")
    await flushPromises()
    expect(client.loginSecondFactor).not.toHaveBeenCalled()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      bindTicket: "tk-1",
      username: "carol",
      password: "secret1",
      code: "123456",
      challengeToken: "ch-1",
    })
    wrapper.unmount()
  })

  it("2FA then 409 ALREADY_LOGGED_IN force retry sends the same challengeToken without a code", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
      )
      .mockRejectedValueOnce(apiError(409, "ALREADY_LOGGED_IN", { device_name: "iPad" }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        completeMfaViaLogin2fa: false,
      },
    })
    await fillAndSubmit(wrapper)
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.find('input[placeholder="000000"]').setValue("123456")
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("强制登录")
    })
    await wrapper.findAll("button").find((b) => b.text() === "强制登录")!.trigger("click")
    await flushPromises()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      bindTicket: "tk-1",
      code: "123456",
      challengeToken: "ch-1",
    })
    expect(bindExisting.mock.calls[2][0]).toMatchObject({
      bindTicket: "tk-1",
      challengeToken: "ch-1",
      force: true,
    })
    expect(bindExisting.mock.calls[2][0].code || "").toBe("")
    wrapper.unmount()
  })

  it("2FA then 409 SSO_ORPHAN_PENDING shows reclaim and resubmits with the same challengeToken", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
      )
      .mockRejectedValueOnce(apiError(409, "SSO_ORPHAN_PENDING", { orphan_username: "ghost" }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        allowReclaim: true,
        completeMfaViaLogin2fa: false,
      },
    })
    await fillAndSubmit(wrapper, "olduser")
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.find('input[placeholder="000000"]').setValue("123456")
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("待审空号 ghost")
    })
    expect(wrapper.find("form.ak-form button").text()).toBe("确认改绑")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      bindTicket: "tk-1",
      code: "123456",
      challengeToken: "ch-1",
    })
    expect(bindExisting.mock.calls[2][0]).toMatchObject({
      reclaim: true,
      challengeToken: "ch-1",
      username: "olduser",
      bindTicket: "tk-1",
    })
    expect(bindExisting.mock.calls[2][0].code || "").toBe("")
    wrapper.unmount()
  })

  it("cancelling 2FA resubmits without challengeToken and can show the dialog again", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
      )
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", { challenge_token: "ch-2", bind_ticket: "tk-1", expires_in: 300 }),
      )
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        completeMfaViaLogin2fa: false,
      },
    })
    await fillAndSubmit(wrapper)
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.findAll("button").find((b) => b.text() === "取消")!.trigger("click")
    await flushPromises()
    expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(false)
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(bindExisting).toHaveBeenCalledTimes(2)
    expect(bindExisting.mock.calls[1][0].challengeToken || "").toBe("")
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    wrapper.unmount()
  })

  it("changing username after SSO_ORPHAN_PENDING clears the challenge token and resets reclaim", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(
        apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
      )
      .mockRejectedValueOnce(apiError(409, "SSO_ORPHAN_PENDING", { orphan_username: "ghost" }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        allowReclaim: true,
        completeMfaViaLogin2fa: false,
      },
    })
    await fillAndSubmit(wrapper, "olduser")
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.find('input[placeholder="000000"]').setValue("123456")
    await flushPromises()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("待审空号 ghost")
    })
    await wrapper.find('input[autocomplete="username"]').setValue("newuser")
    await flushPromises()
    expect(wrapper.text()).not.toContain("待审空号 ghost")
    expect(wrapper.find("form.ak-form button").text()).not.toBe("确认改绑")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(wrapper.emitted("success")).toBeTruthy()
    expect(bindExisting.mock.calls[2][0]).toMatchObject({
      username: "newuser",
      bindTicket: "tk-1",
    })
    expect(bindExisting.mock.calls[2][0].challengeToken || "").toBe("")
    expect(bindExisting.mock.calls[2][0].reclaim).toBeFalsy()
    wrapper.unmount()
  })

  it("WeChat MFA completes via loginSecondFactor", async () => {
    const client = mockClient()
    client.loginSecondFactor.mockResolvedValue({ access_token: "tok", token_type: "bearer" })
    const bindExisting = vi.fn().mockRejectedValueOnce(
      apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
    )
    const wrapper = mount(BindExistingAccountForm, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        bindExisting,
        completeMfaViaLogin2fa: true,
      },
    })
    await fillAndSubmit(wrapper)
    await vi.waitFor(() => {
      expect(wrapper.find('input[placeholder="000000"]').exists()).toBe(true)
    })
    await wrapper.find('input[placeholder="000000"]').setValue("123456")
    await flushPromises()
    expect(client.loginSecondFactor).toHaveBeenCalled()
    expect(bindExisting).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted("success")).toBeTruthy()
    wrapper.unmount()
  })
})
