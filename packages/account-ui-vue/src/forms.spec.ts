import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import { type AccountClient } from "./client"
import { LoginForm } from "./forms"

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
