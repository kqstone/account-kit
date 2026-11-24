import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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

async function fillAndSubmit(username = "carol", password = "secret1") {
  fireEvent.change(screen.getByLabelText(/用户名/), { target: { value: username } })
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } })
  fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
}

describe("BindExistingAccountForm", () => {
  afterEach(() => {
    cleanup()
  })

  it("accepts username or email and posts the same payload", async () => {
    const client = mockClient()
    const bindExisting = vi.fn(async (payload: BindExistingPayload) => {
      expect(payload.username).toBe("ada@example.com")
      expect(payload.password).toBe("secret1")
      expect(payload.bindTicket).toBe("tk-1")
      return { access_token: "tok", token_type: "bearer" } as TokenPair
    })
    const onSuccess = vi.fn()
    render(
      <BindExistingAccountForm
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        bindExisting={bindExisting}
        allowReclaim
        onSuccess={onSuccess}
      />,
    )
    expect(screen.getByLabelText("用户名或邮箱")).toBeTruthy()
    await fillAndSubmit("ada@example.com")
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(bindExisting).toHaveBeenCalledTimes(1)
  })

  it("shows captcha then retries with captcha fields", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(apiError(428, "CAPTCHA_REQUIRED", { captcha_required: true }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    render(
      <BindExistingAccountForm
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        bindExisting={bindExisting}
        onSuccess={() => undefined}
      />,
    )
    await fillAndSubmit()
    await waitFor(() => expect(screen.getByPlaceholderText("输入图中字符")).toBeTruthy())
    fireEvent.change(screen.getByPlaceholderText("输入图中字符"), { target: { value: "ABCD" } })
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(bindExisting).toHaveBeenCalledTimes(2))
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      captchaId: "cid-1",
      captchaCode: "ABCD",
      bindTicket: "tk-1",
    })
  })

  it("asks for reclaim confirm then resubmits with reclaim true", async () => {
    const client = mockClient()
    const bindExisting = vi
      .fn()
      .mockRejectedValueOnce(apiError(409, "SSO_ORPHAN_PENDING", { orphan_username: "ghost" }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const onSuccess = vi.fn()
    render(
      <BindExistingAccountForm
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        bindExisting={bindExisting}
        allowReclaim
        onSuccess={onSuccess}
      />,
    )
    await fillAndSubmit("olduser")
    await waitFor(() => expect(screen.getByText(/待审空号 ghost/)).toBeTruthy())
    fireEvent.click(screen.getByText("确认改绑"))
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(bindExisting.mock.calls[1][0]).toMatchObject({ reclaim: true, username: "olduser", bindTicket: "tk-1" })
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
    const onSuccess = vi.fn()
    render(
      <BindExistingAccountForm
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        bindExisting={bindExisting}
        completeMfaViaLogin2fa={false}
        onSuccess={onSuccess}
      />,
    )
    await fillAndSubmit()
    await waitFor(() => expect(screen.getByPlaceholderText("000000")).toBeTruthy())
    fireEvent.click(screen.getByText("跳过两步验证（发送邮箱验证码登录）"))
    await waitFor(() => expect(client.sendLoginEmailCode).toHaveBeenCalledWith("ch-1", "zh-CN"))
    fireEvent.click(screen.getByText("使用验证器验证码"))
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "123456" } })
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(client.loginSecondFactor).not.toHaveBeenCalled()
    expect(bindExisting.mock.calls[1][0]).toMatchObject({
      bindTicket: "tk-1",
      username: "carol",
      password: "secret1",
      code: "123456",
    })
  })

  it("WeChat MFA completes via loginSecondFactor", async () => {
    const client = mockClient()
    client.loginSecondFactor.mockResolvedValue({ access_token: "tok", token_type: "bearer" })
    const bindExisting = vi.fn().mockRejectedValueOnce(
      apiError(401, "MFA_REQUIRED", { challenge_token: "ch-1", bind_ticket: "tk-1", expires_in: 300 }),
    )
    const onSuccess = vi.fn()
    render(
      <BindExistingAccountForm
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        bindExisting={bindExisting}
        completeMfaViaLogin2fa
        onSuccess={onSuccess}
      />,
    )
    await fillAndSubmit()
    await waitFor(() => expect(screen.getByPlaceholderText("000000")).toBeTruthy())
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "123456" } })
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(client.loginSecondFactor).toHaveBeenCalled()
    expect(bindExisting).toHaveBeenCalledTimes(1)
  })
})
