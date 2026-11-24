import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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
  afterEach(() => cleanup())

  it("renders pending / rejected / approved tones", () => {
    const { rerender } = render(<ApprovalStatusBadge status="pending" />)
    expect(screen.getByText("待审批").className).toContain("ak-approval-pending")
    rerender(<ApprovalStatusBadge status="rejected" />)
    expect(screen.getByText("未通过").className).toContain("ak-approval-rejected")
    rerender(<ApprovalStatusBadge status="approved" />)
    expect(screen.getByText("已通过").className).toContain("ak-approval-approved")
  })
})

describe("SsoBindPanel", () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it("shows identity summary, bind vs create, and hides create when allowCreate is false", async () => {
    const client = mockClient()
    const { unmount } = render(
      <SsoBindPanel
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        expiresIn={600}
        identity={{ email: "new@example.com", name: "Ada", email_verified: true }}
        allowCreate
        onSuccess={() => undefined}
      />,
    )
    expect(screen.getByText(/Ada/)).toBeTruthy()
    expect(screen.getByText(/new@example.com/)).toBeTruthy()
    expect(screen.getAllByText("绑定已有账号").length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "创建新账号" })).toBeTruthy()
    expect(screen.getByLabelText("用户名或邮箱")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "创建新账号" }))
    expect(screen.getByText("将用 new@example.com 创建新账号")).toBeTruthy()
    unmount()

    render(
      <SsoBindPanel
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        expiresIn={600}
        allowCreate={false}
        onSuccess={() => undefined}
      />,
    )
    expect(screen.queryByRole("button", { name: "创建新账号" })).toBeNull()
    expect(screen.getByLabelText("用户名或邮箱")).toBeTruthy()
  })

  it("expires the ticket and offers back-to-login", async () => {
    vi.useFakeTimers()
    const onExpired = vi.fn()
    render(
      <SsoBindPanel
        client={mockClient() as unknown as AccountClient}
        bindTicket="tk-1"
        expiresIn={2}
        onSuccess={() => undefined}
        onExpired={onExpired}
      />,
    )
    expect(screen.getByText("2 秒后失效")).toBeTruthy()
    await act(async () => {
      vi.advanceTimersByTime(2500)
    })
    expect(screen.getByText(/绑定凭证已过期/)).toBeTruthy()
    fireEvent.click(screen.getByText("返回登录"))
    expect(onExpired).toHaveBeenCalled()
  })

  it("create-account pending does not call onSuccess", async () => {
    const client = mockClient()
    client.ssoCreateAccount.mockResolvedValue({
      status: "pending",
      user: { id: "u1", username: "ada", approval_status: "pending" },
    })
    const onSuccess = vi.fn()
    const onPending = vi.fn()
    render(
      <SsoBindPanel
        client={client as unknown as AccountClient}
        bindTicket="tk-1"
        identity={{ email: "ada@example.com" }}
        onSuccess={onSuccess}
        onPending={onPending}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "创建新账号" }))
    fireEvent.click(document.querySelector(".ak-form button") as HTMLButtonElement)
    await waitFor(() => expect(onPending).toHaveBeenCalled())
    expect(onSuccess).not.toHaveBeenCalled()
    expect(client.ssoCreateAccount).toHaveBeenCalledWith({ bindTicket: "tk-1", force: false, deviceName: "" })
  })
})

describe("SsoBindSettings", () => {
  afterEach(() => cleanup())

  it("starts bind by assigning the host URL", async () => {
    const assign = vi.fn()
    vi.stubGlobal("location", { ...window.location, assign })
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: false })
    client.ssoBindStart.mockResolvedValue({ url: "https://idp.example/authorize" })
    render(<SsoBindSettings client={client as unknown as AccountClient} token="tok" />)
    await waitFor(() => expect(screen.getByText("绑定成龈之美")).toBeTruthy())
    fireEvent.click(screen.getByText("绑定成龈之美"))
    await waitFor(() => expect(client.ssoBindStart).toHaveBeenCalledWith("tok"))
    expect(assign).toHaveBeenCalledWith("https://idp.example/authorize")
    vi.unstubAllGlobals()
  })

  it("shows masked email and blocks unbind when password_set is false", async () => {
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: true, email_masked: "a***@ex.com" })
    const onNeedPassword = vi.fn()
    render(
      <SsoBindSettings
        client={client as unknown as AccountClient}
        token="tok"
        passwordSet={false}
        onNeedPassword={onNeedPassword}
      />,
    )
    await waitFor(() => expect(screen.getByText(/a\*\*\*@ex.com/)).toBeTruthy())
    const submit = screen.getByText("确认解绑") as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(screen.getByText("请先设置密码再解绑成龈之美")).toBeTruthy()
    expect(client.ssoUnbind).not.toHaveBeenCalled()
  })

  it("unbinds with password and optional 2FA code", async () => {
    const client = mockClient()
    client.ssoBinding.mockResolvedValue({ bound: true, email_masked: "a***@ex.com" })
    client.ssoUnbind.mockResolvedValue({ bound: false })
    render(<SsoBindSettings client={client as unknown as AccountClient} token="tok" passwordSet />)
    await waitFor(() => expect(screen.getByText("确认解绑")).toBeTruthy())
    const fields = document.querySelectorAll("form.ak-form input")
    fireEvent.change(fields[0], { target: { value: "secret1" } })
    fireEvent.change(fields[1], { target: { value: "123456" } })
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(client.ssoUnbind).toHaveBeenCalledWith("tok", { password: "secret1", code: "123456" }))
    expect(screen.getByText("成龈之美已解绑")).toBeTruthy()
  })
})
