import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AccountApiError, type AccountClient } from "./client"
import { WechatQrLogin } from "./wechat"

function apiError(status: number, code: string, extra: Record<string, unknown> = {}) {
  const detail = extra.detail !== undefined ? extra.detail : { code, message: code, ...extra }
  return new AccountApiError(code, status, { detail, code })
}

function mockClient() {
  let captchaSeq = 0
  return {
    startWechatLogin: vi.fn().mockResolvedValue({
      ticket: "ticket-1",
      scene: "scene-1",
      expires_in: 120,
      image_base64: "qr",
      mime: "image/png",
    }),
    wechatLoginStatus: vi.fn().mockResolvedValue({ status: "unbound", bind_ticket: "ticket-1" }),
    cancelWechatLogin: vi.fn().mockResolvedValue({ status: "ok" }),
    captcha: vi.fn(async () => {
      captchaSeq += 1
      return { captcha_id: `cid-${captchaSeq}`, image_base64: `img${captchaSeq}`, expires_in: 300 }
    }),
    wechatBindExisting: vi.fn(),
  }
}

type TestClient = ReturnType<typeof mockClient>

async function reachBindForm(client: TestClient) {
  render(<WechatQrLogin client={client as unknown as AccountClient} pollMs={500} onSuccess={() => undefined} />)
  await screen.findByText("该微信尚未绑定账号，请在下方绑定已有账号或注册新账号。", {}, { timeout: 3000 })
}

function bindForm() {
  return document.querySelector("form.ak-form") as HTMLFormElement
}

async function fillAndSubmit(username = "carol", password = "secret1") {
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: username } })
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } })
  fireEvent.submit(bindForm())
}

describe("WechatQrLogin bind-existing captcha", () => {
  afterEach(() => {
    cleanup()
  })

  it("does not show captcha when the server does not require it", async () => {
    const client = mockClient()
    client.wechatBindExisting.mockRejectedValue(apiError(401, "INVALID_CREDENTIALS", { detail: "用户名或密码错误" }))
    await reachBindForm(client)
    expect(screen.queryByPlaceholderText("输入图中字符")).toBeNull()
    await fillAndSubmit()
    await waitFor(() => expect(client.wechatBindExisting).toHaveBeenCalled())
    expect(screen.queryByPlaceholderText("输入图中字符")).toBeNull()
    expect(client.captcha).not.toHaveBeenCalled()
    expect(client.wechatBindExisting.mock.calls[0][0].captchaId).toBeUndefined()
    expect(client.wechatBindExisting.mock.calls[0][0].captchaCode).toBeUndefined()
  })

  it("shows captcha when required, refreshes, retries with captcha fields, and swaps image after failure", async () => {
    const client = mockClient()
    client.wechatBindExisting
      .mockRejectedValueOnce(apiError(428, "CAPTCHA_REQUIRED", { captcha_required: true }))
      .mockRejectedValueOnce(apiError(400, "CAPTCHA_INVALID", { captcha_required: true }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    await reachBindForm(client)
    expect(screen.queryByPlaceholderText("输入图中字符")).toBeNull()

    await fillAndSubmit()
    await waitFor(() => expect(screen.getByPlaceholderText("输入图中字符")).toBeTruthy())
    expect(client.captcha).toHaveBeenCalledTimes(1)
    expect((screen.getByAltText("captcha") as HTMLImageElement).src).toContain("img1")

    fireEvent.click(screen.getByText("换一张"))
    await waitFor(() => expect(client.captcha).toHaveBeenCalledTimes(2))
    expect((screen.getByAltText("captcha") as HTMLImageElement).src).toContain("img2")

    fireEvent.change(screen.getByPlaceholderText("输入图中字符"), { target: { value: "ABCD" } })
    fireEvent.submit(bindForm())
    await waitFor(() => expect(client.wechatBindExisting).toHaveBeenCalledTimes(2))
    expect(client.wechatBindExisting.mock.calls[1][0]).toMatchObject({
      bindTicket: "ticket-1",
      username: "carol",
      password: "secret1",
      captchaId: "cid-2",
      captchaCode: "ABCD",
    })
    await waitFor(() => expect(client.captcha).toHaveBeenCalledTimes(3))
    expect((screen.getByAltText("captcha") as HTMLImageElement).src).toContain("img3")
    expect(screen.getByText("图形验证码错误或已失效，请重试")).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText("输入图中字符"), { target: { value: "ABCD" } })
    fireEvent.submit(bindForm())
    await waitFor(() => expect(client.wechatBindExisting).toHaveBeenCalledTimes(3))
    expect(client.wechatBindExisting.mock.calls[2][0]).toMatchObject({
      captchaId: "cid-3",
      captchaCode: "ABCD",
    })
  })
})
