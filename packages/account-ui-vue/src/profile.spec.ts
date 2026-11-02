import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
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
  it("password_set=false shows Set password, hides old password, requires email code", async () => {
    const client = mockClient()
    const wrapper = mount(ProfileFields, {
      props: { client: client as unknown as AccountClient, token: "t", user: { ...baseUser, password_set: false }, language: "zh-CN" },
    })
    expect(wrapper.find("h3").text()).toBe("设置密码")
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(false)
    expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(true)
    const send = wrapper.findAll("button").find((b) => b.text() === "发送验证码")!
    await send.trigger("click")
    await flushPromises()
    expect(client.sendCode).toHaveBeenCalledWith("sso@example.com", "change_password", "zh-CN", "t")
    const pw = wrapper.findAll('input[autocomplete="new-password"]')
    await pw[0].setValue("secret2")
    await pw[1].setValue("secret2")
    await wrapper.find('input[autocomplete="one-time-code"]').setValue("123456")
    await wrapper.find("form").trigger("submit")
    await flushPromises()
    expect(client.changePassword).toHaveBeenCalledWith("t", "", "secret2", "123456")
    wrapper.unmount()
  })

  it("English label is pure English", () => {
    const wrapper = mount(ProfileFields, {
      props: { client: mockClient() as unknown as AccountClient, token: "t", user: { ...baseUser, password_set: false }, language: "en" },
    })
    expect(wrapper.find("h3").text()).toBe("Set password")
    wrapper.unmount()
  })

  it("password_set true/absent keeps Change password with old password", () => {
    const wrapper = mount(ProfileFields, {
      props: { client: mockClient() as unknown as AccountClient, token: "t", user: baseUser, language: "zh-CN" },
    })
    expect(wrapper.find("h3").text()).toBe("修改密码")
    expect(wrapper.find('input[autocomplete="current-password"]').exists()).toBe(true)
    expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
