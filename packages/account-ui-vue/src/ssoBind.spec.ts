import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import { type AccountClient } from "./client"
import { ApprovalStatusBadge, SsoBindPanel, SsoBindSettings } from "./ssoBind"

function mockClient(extra: Record<string, unknown> = {}) {
  return {
    ssoBindExisting: vi.fn(),
    ssoCreateAccount: vi.fn(),
    ssoBindStart: vi.fn(),
    ssoBinding: vi.fn(),
    ssoUnbind: vi.fn(),
    captcha: vi.fn(),
    loginSecondFactor: vi.fn(),
    sendLoginEmailCode: vi.fn(),
    ...extra,
  }
}

describe("ApprovalStatusBadge", () => {
  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("renders pending / rejected / approved tones", () => {
    const pending = mount(ApprovalStatusBadge, { props: { status: "pending" } })
    expect(pending.text()).toBe("待审批")
    expect(pending.classes().join(" ")).toContain("ak-approval-pending")
    pending.unmount()
    const rejected = mount(ApprovalStatusBadge, { props: { status: "rejected" } })
    expect(rejected.text()).toBe("未通过")
    expect(rejected.classes().join(" ")).toContain("ak-approval-rejected")
    rejected.unmount()
    const approved = mount(ApprovalStatusBadge, { props: { status: "approved" } })
    expect(approved.text()).toBe("已通过")
    expect(approved.classes().join(" ")).toContain("ak-approval-approved")
    approved.unmount()
  })
})

describe("SsoBindPanel", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.useRealTimers()
  })

  it("shows identity summary, bind vs create, and hides create when allowCreate is false", async () => {
    const client = mockClient()
    const wrapper = mount(SsoBindPanel, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        expiresIn: 600,
        identity: { email: "new@example.com", name: "Ada", email_verified: true },
        allowCreate: true,
      },
    })
    expect(wrapper.text()).toContain("Ada")
    expect(wrapper.text()).toContain("new@example.com")
    expect(wrapper.text()).toContain("绑定已有账号")
    expect(wrapper.text()).toContain("创建新账号")
    expect(wrapper.text()).toContain("用户名或邮箱")
    const createTab = wrapper.findAll("button").find((b) => b.text() === "创建新账号")!
    await createTab.trigger("click")
    expect(wrapper.text()).toContain("将用 new@example.com 创建新账号")
    wrapper.unmount()

    const onlyBind = mount(SsoBindPanel, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        expiresIn: 600,
        allowCreate: false,
      },
    })
    expect(onlyBind.findAll("button").some((b) => b.text() === "创建新账号")).toBe(false)
    expect(onlyBind.text()).toContain("用户名或邮箱")
    onlyBind.unmount()
  })

  it("expires the ticket and offers back-to-login", async () => {
    vi.useFakeTimers()
    const wrapper = mount(SsoBindPanel, {
      props: {
        client: mockClient() as unknown as AccountClient,
        bindTicket: "tk-1",
        expiresIn: 2,
      },
    })
    expect(wrapper.text()).toContain("2 秒后失效")
    vi.advanceTimersByTime(2000)
    await flushPromises()
    expect(wrapper.text()).toContain("绑定凭证已过期")
    await wrapper.findAll("button").find((b) => b.text() === "返回登录")!.trigger("click")
    expect(wrapper.emitted("expired")).toBeTruthy()
    wrapper.unmount()
  })

  it("create-account pending does not emit success", async () => {
    const client = mockClient()
    client.ssoCreateAccount.mockResolvedValue({
      status: "pending",
      user: { id: "u1", username: "ada", approval_status: "pending" },
    })
    const wrapper = mount(SsoBindPanel, {
      props: {
        client: client as unknown as AccountClient,
        bindTicket: "tk-1",
        identity: { email: "ada@example.com" },
      },
    })
    await wrapper.findAll("button").find((b) => b.text() === "创建新账号")!.trigger("click")
    await wrapper.find(".ak-form button").trigger("click")
    await flushPromises()
    expect(wrapper.emitted("pending")).toBeTruthy()
    expect(wrapper.emitted("success")).toBeFalsy()
    expect(client.ssoCreateAccount).toHaveBeenCalledWith({ bindTicket: "tk-1", force: false, deviceName: "" })
    wrapper.unmount()
  })
})

describe("SsoBindSettings", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.unstubAllGlobals()
  })

  it("starts bind by assigning the host URL", async () => {
    const assign = vi.fn()
    vi.stubGlobal("location", { assign })
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: false })
    client.ssoBindStart.mockResolvedValue({ url: "https://idp.example/authorize" })
    const wrapper = mount(SsoBindSettings, {
      props: { client: client as unknown as AccountClient, token: "tok" },
    })
    await flushPromises()
    await wrapper.findAll("button").find((b) => b.text() === "绑定成龈之美")!.trigger("click")
    await flushPromises()
    expect(client.ssoBindStart).toHaveBeenCalledWith("tok")
    expect(assign).toHaveBeenCalledWith("https://idp.example/authorize")
    wrapper.unmount()
  })

  it("shows masked email and blocks unbind when password_set is false", async () => {
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: true, email_masked: "a***@ex.com" })
    const wrapper = mount(SsoBindSettings, {
      props: { client: client as unknown as AccountClient, token: "tok", passwordSet: false },
    })
    await flushPromises()
    expect(wrapper.text()).toContain("a***@ex.com")
    const submit = wrapper.find("form.ak-form button")
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain("请先设置密码再解绑成龈之美")
    expect(client.ssoUnbind).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("unbinds with password and optional 2FA code", async () => {
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: true, email_masked: "a***@ex.com" })
    client.ssoUnbind.mockResolvedValue({ bound: false })
    const wrapper = mount(SsoBindSettings, {
      props: { client: client as unknown as AccountClient, token: "tok", passwordSet: true },
    })
    await flushPromises()
    const inputs = wrapper.findAll("form.ak-form input")
    await inputs[0].setValue("secret1")
    await inputs[1].setValue("123456")
    await wrapper.find("form.ak-form").trigger("submit")
    await flushPromises()
    expect(client.ssoUnbind).toHaveBeenCalledWith("tok", { password: "secret1", code: "123456" })
    expect(wrapper.text()).toContain("成龈之美已解绑")
    wrapper.unmount()
  })
})
