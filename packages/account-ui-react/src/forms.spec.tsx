import { cleanup, fireEvent, render, waitFor } from "@testing-library/react"
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
    cleanup()
    document.body.innerHTML = ""
  })

  it("prefills defaultUsername/defaultPassword and sets name/autocomplete", () => {
    const client = mockClient()
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="alice"
        defaultPassword="secret1"
        onSuccess={() => undefined}
      />,
    )
    const user = document.querySelector('input[name="username"]') as HTMLInputElement
    const pass = document.querySelector('input[name="password"]') as HTMLInputElement
    expect(user.autocomplete).toBe("username")
    expect(pass.autocomplete).toBe("current-password")
    expect(user.value).toBe("alice")
    expect(pass.value).toBe("secret1")
  })

  it("beforeSubmit false aborts login; async false too", async () => {
    const client = mockClient()
    const before = vi.fn().mockReturnValue(false)
    const { unmount } = render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="carol"
        defaultPassword="secret1"
        beforeSubmit={before}
        onSuccess={() => undefined}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(before).toHaveBeenCalled())
    expect(before).toHaveBeenCalledWith({ username: "carol", password: "secret1" })
    expect(client.login).not.toHaveBeenCalled()
    unmount()

    const asyncFalse = vi.fn().mockResolvedValue(false)
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="carol"
        defaultPassword="secret1"
        beforeSubmit={asyncFalse}
        onSuccess={() => undefined}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(asyncFalse).toHaveBeenCalled())
    expect(client.login).not.toHaveBeenCalled()
  })

  it("onSuccess receives credentials as the second argument", async () => {
    const client = mockClient()
    const onSuccess = vi.fn()
    render(
      <LoginForm
        client={client as unknown as AccountClient}
        defaultUsername="dave"
        defaultPassword="secret1"
        onSuccess={onSuccess}
      />,
    )
    fireEvent.submit(document.querySelector("form.ak-form") as HTMLFormElement)
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(onSuccess.mock.calls[0][0]).toBe("tok")
    expect(onSuccess.mock.calls[0][1]).toMatchObject({ username: "dave", password: "secret1" })
  })
})
