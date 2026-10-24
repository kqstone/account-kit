import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
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
  const wrapper = mount(WechatQrLogin, {
    props: { client: client as unknown as AccountClient, pollMs: 500 },
  })
  await vi.waitFor(
    () => {
      expect(wrapper.text()).toContain("绑定已有账号")
    },
    { timeout: 3000 },
  )
  return wrapper
}

async function fillAndSubmit(wrapper: VueWrapper, username = "carol", password = "secret1") {
  await wrapper.find('input[autocomplete="username"]').setValue(username)
  await wrapper.find('input[autocomplete="current-password"]').setValue(password)
  await wrapper.find("form.ak-form").trigger("submit")
  await flushPromises()
}

describe("WechatQrLogin bind-existing captcha", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("does not show captcha when the server does not require it", async () => {
    const client = mockClient()
    client.wechatBindExisting.mockRejectedValue(apiError(401, "INVALID_CREDENTIALS", { detail: "用户名或密码错误" }))
    const wrapper = await reachBindForm(client)
    expect(wrapper.find('input[placeholder="输入图中字符"]').exists()).toBe(false)
    await fillAndSubmit(wrapper)
    expect(wrapper.find('input[placeholder="输入图中字符"]').exists()).toBe(false)
    expect(client.captcha).not.toHaveBeenCalled()
    expect(client.wechatBindExisting).toHaveBeenCalledWith(
      expect.objectContaining({ username: "carol", password: "secret1" }),
    )
    expect(client.wechatBindExisting.mock.calls[0][0].captchaId).toBeUndefined()
    expect(client.wechatBindExisting.mock.calls[0][0].captchaCode).toBeUndefined()
    wrapper.unmount()
  })

  it("shows captcha when required, refreshes, retries with captcha fields, and swaps image after failure", async () => {
    const client = mockClient()
    client.wechatBindExisting
      .mockRejectedValueOnce(apiError(428, "CAPTCHA_REQUIRED", { captcha_required: true }))
      .mockRejectedValueOnce(apiError(400, "CAPTCHA_INVALID", { captcha_required: true }))
      .mockResolvedValueOnce({ access_token: "tok", token_type: "bearer" })
    const wrapper = await reachBindForm(client)
    expect(wrapper.find('input[placeholder="输入图中字符"]').exists()).toBe(false)

    await fillAndSubmit(wrapper)
    expect(wrapper.find('input[placeholder="输入图中字符"]').exists()).toBe(true)
    expect(client.captcha).toHaveBeenCalledTimes(1)
    const firstSrc = wrapper.find('img[alt="captcha"]').attributes("src")
    expect(firstSrc).toContain("img1")

    await wrapper.findAll("button").find((btn) => btn.text() === "换一张")!.trigger("click")
    await flushPromises()
    expect(client.captcha).toHaveBeenCalledTimes(2)
    expect(wrapper.find('img[alt="captcha"]').attributes("src")).toContain("img2")

    await wrapper.find('input[placeholder="输入图中字符"]').setValue("ABCD")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(client.wechatBindExisting).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        bindTicket: "ticket-1",
        username: "carol",
        password: "secret1",
        captchaId: "cid-2",
        captchaCode: "ABCD",
      }),
    )
    expect(client.captcha).toHaveBeenCalledTimes(3)
    expect(wrapper.find('img[alt="captcha"]').attributes("src")).toContain("img3")
    expect(wrapper.text()).toContain("图形验证码错误或已失效")

    await wrapper.find('input[placeholder="输入图中字符"]').setValue("ABCD")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(client.wechatBindExisting.mock.calls[2][0]).toMatchObject({
      captchaId: "cid-3",
      captchaCode: "ABCD",
    })
    wrapper.unmount()
  })
})
