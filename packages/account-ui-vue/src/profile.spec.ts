import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import { type AccountClient, type AccountUser } from "./client"
import * as kit from "./index"
import { PasswordForm, ProfileFields } from "./profile"

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
    expect(wrapper.text()).toContain("验证码已发送至 sso@example.com")
    expect(wrapper.find("button.ak-code-btn").text()).toBe("120 秒后重发")
    const pw = wrapper.findAll('input[autocomplete="new-password"]')
    await pw[0].setValue("secret2")
    await pw[1].setValue("secret2")
    await wrapper.find('input[autocomplete="one-time-code"]').setValue("123456")
    await wrapper.find("form.ak-password-form").trigger("submit")
    await flushPromises()
    expect(client.changePassword).toHaveBeenCalledWith("t", "", "secret2", "123456")
    expect(wrapper.findComponent(PasswordForm).exists()).toBe(true)
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

  it("exports PasswordForm and ProfileFields reuses it", () => {
    expect(kit.PasswordForm).toBe(PasswordForm)
    const wrapper = mount(ProfileFields, {
      props: { client: mockClient() as unknown as AccountClient, token: "t", user: { ...baseUser, password_set: false } },
    })
    expect(wrapper.find("form.ak-password-form").exists()).toBe(true)
    expect(wrapper.findAll("form").length).toBe(2)
    wrapper.unmount()
  })

  it("PasswordForm hides profile fields and switches set vs change", () => {
    const setWrapper = mount(PasswordForm, {
      props: { client: mockClient() as unknown as AccountClient, token: "t", user: { ...baseUser, password_set: false } },
    })
    expect(setWrapper.find("h3").text()).toBe("设置密码")
    expect(setWrapper.find('input[autocomplete="current-password"]').exists()).toBe(false)
    expect(setWrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(true)
    expect(setWrapper.text()).not.toContain("姓名")
    setWrapper.unmount()

    const change = mount(PasswordForm, {
      props: { client: mockClient() as unknown as AccountClient, token: "t", user: baseUser },
    })
    expect(change.find("h3").text()).toBe("修改密码")
    expect(change.find('input[autocomplete="current-password"]').exists()).toBe(true)
    expect(change.find('input[autocomplete="one-time-code"]').exists()).toBe(false)
    change.unmount()
  })
})
