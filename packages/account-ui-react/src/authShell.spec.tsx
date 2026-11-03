import { cleanup, fireEvent, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AuthShell, CodeInputRow } from "./authShell"
import { CODE_ROW_CSS, detectNative, SHELL_CSS, systemLocale } from "./shellStyle"

function selectors(css: string): string[] {
  const out: string[] = []
  const stripped = css.replace(/@media[^{]*\{/g, "")
  for (const m of stripped.matchAll(/([^{}]+)\{[^{}]*\}/g)) out.push(...m[1].split(",").map((s) => s.trim()).filter(Boolean))
  return out
}

afterEach(() => {
  cleanup()
  document.body.innerHTML = ""
  delete (globalThis as { Capacitor?: unknown }).Capacitor
})

describe("AuthShell", () => {
  it("renders brand, header, scroll body, card footer, copyright, lang and extra in place", () => {
    render(
      <AuthShell brandName="Brand" brandSubtitle="Sub" logo={<i data-testid="logo" />} title="登录" subtitle="欢迎" footer={<a href="#r">注册</a>} copyright="© 2026" languageSwitch={<span data-testid="lang" />} extra={<div data-testid="modal" />} native={false}>
        <form data-testid="form" />
      </AuthShell>,
    )
    const shell = document.querySelector(".ak-shell")!
    expect(shell.classList.contains("is-web")).toBe(true)
    expect(shell.querySelector(".ak-shell-lang [data-testid=lang]")).not.toBeNull()
    expect(shell.querySelector(".ak-shell-header .ak-shell-logo [data-testid=logo]")).not.toBeNull()
    expect(shell.querySelector(".ak-shell-brand-name")!.textContent).toBe("Brand")
    const card = shell.querySelector(".ak-shell-main > .ak-shell-card")!
    expect(Array.from(card.children).map((c) => c.className)).toEqual(["ak-shell-card-header", "ak-shell-body", "ak-shell-card-footer"])
    expect(card.querySelector(".ak-shell-body [data-testid=form]")).not.toBeNull()
    const copy = Array.from(shell.children).find((c) => c.classList.contains("ak-shell-footer"))!
    expect(copy.textContent).toBe("© 2026")
    const modal = shell.querySelector("[data-testid=modal]")!
    expect(modal.parentElement).toBe(shell)
    expect(modal.closest(".ak-shell-body")).toBeNull()
  })

  it("hides language switch and copyright when native", () => {
    render(<AuthShell native copyright="©" languageSwitch={<span />} brandName="B" />)
    expect(document.querySelector(".ak-shell.is-native")).not.toBeNull()
    expect(document.querySelector(".ak-shell-lang")).toBeNull()
    expect(document.querySelector(".ak-shell-footer")).toBeNull()
  })

  it("defaults native from Capacitor and allows explicit overrides", () => {
    ;(globalThis as { Capacitor?: unknown }).Capacitor = { isNativePlatform: () => true }
    expect(detectNative()).toBe(true)
    render(<AuthShell copyright="©" languageSwitch={<span />} showCopyright />)
    expect(document.querySelector(".ak-shell-lang")).toBeNull()
    expect(document.querySelector(".ak-shell-footer")).not.toBeNull()
  })

  it("only the body scrolls: CSS rules", () => {
    const css = (CODE_ROW_CSS + SHELL_CSS).replace(/\s+/g, " ")
    expect(css).toMatch(/\.ak-shell\{[^}]*height:100dvh[^}]*overflow:hidden/)
    expect(css).toMatch(/\.ak-shell-body\{[^}]*min-height:0;overflow-y:auto[^}]*overscroll-behavior:contain/)
    expect(css).toMatch(/\.ak-shell-card\{[^}]*max-height:100%[^}]*overflow:hidden/)
    expect(css).toMatch(/\.ak-shell-header\{flex-shrink:0/)
    expect(css).toMatch(/\.ak-shell-card-header\{flex-shrink:0/)
    expect(css).toMatch(/\.ak-shell-card-footer\{flex-shrink:0/)
    expect(css).toMatch(/\.ak-shell-footer\{flex-shrink:0/)
    for (const v of ["--ak-shell-bg", "--ak-shell-primary", "--ak-shell-card-bg", "--ak-shell-card-radius", "--ak-control-height"]) expect(css).toContain(`var(${v}`)
    expect(css).not.toContain("#4f46e5")
  })

  it("does not style slot controls: every selector is scoped, none targets bare input/button", () => {
    for (const sel of selectors(CODE_ROW_CSS + SHELL_CSS)) {
      expect(sel.startsWith(".ak-"), sel).toBe(true)
      const parts = sel.split(/\s+|>/).filter(Boolean)
      parts.forEach((part, i) => {
        if (!/^(input|button|select|textarea|label|a|form)\b/.test(part)) return
        // bare elements only allowed inside kit-owned containers (.ak-form / card footer links)
        const owned = parts.slice(0, i).some((p) => p === ".ak-form" || p === ".ak-shell-card-footer")
        expect(owned, sel).toBe(true)
      })
    }
    render(
      <AuthShell native={false}>
        <div className="el-form">
          <input className="el-input__inner" data-testid="el" />
          <button className="el-button" data-testid="btn">x</button>
        </div>
      </AuthShell>,
    )
    const el = document.querySelector("[data-testid=el]") as HTMLInputElement
    const btn = document.querySelector("[data-testid=btn]") as HTMLButtonElement
    expect(getComputedStyle(el).height).not.toBe("40px")
    expect(getComputedStyle(btn).backgroundColor).not.toMatch(/37, 99, 235|#2563eb/)
  })

  it("brand click works with mouse and keyboard; headerAttrs pass through", () => {
    const onBrand = vi.fn()
    render(<AuthShell brandName="B" onBrandClick={onBrand} headerAttrs={{ "data-tauri-drag-region": "" }} native={false} />)
    const brand = document.querySelector(".ak-shell-brand")!
    expect(brand.getAttribute("role")).toBe("button")
    expect(brand.getAttribute("tabindex")).toBe("0")
    fireEvent.click(brand)
    fireEvent.keyDown(brand, { key: "Enter" })
    fireEvent.keyDown(brand, { key: " " })
    fireEvent.keyDown(brand, { key: "a" })
    expect(onBrand).toHaveBeenCalledTimes(3)
    expect(document.querySelector("header.ak-shell-header")!.hasAttribute("data-tauri-drag-region")).toBe(true)
  })

  it("systemLocale returns navigator language", () => {
    expect(typeof systemLocale()).toBe("string")
    expect(systemLocale().length).toBeGreaterThan(0)
  })
})

describe("CodeInputRow", () => {
  it("puts the label outside the row and keeps .ak-row", () => {
    const onChange = vi.fn()
    const onClick = vi.fn()
    render(<CodeInputRow label="验证码" value="" onChange={onChange} buttonText="发送" onButtonClick={onClick} maxLength={6} />)
    const field = document.querySelector(".ak-code-field")!
    expect(Array.from(field.children).map((c) => c.tagName + "." + c.className)).toEqual(["LABEL.ak-field-label", "DIV.ak-code-row ak-row"])
    const row = field.querySelector(".ak-code-row")!
    expect(Array.from(row.children).map((c) => c.tagName)).toEqual(["INPUT", "BUTTON"])
    const input = row.querySelector("input")!
    expect((field.querySelector("label") as HTMLLabelElement).htmlFor).toBe(input.id)
    fireEvent.change(input, { target: { value: "123" } })
    expect(onChange).toHaveBeenCalledWith("123")
    fireEvent.click(row.querySelector("button")!)
    expect(onClick).toHaveBeenCalled()
  })

  it("renders captcha image between input and button", () => {
    render(<CodeInputRow value="" onChange={() => undefined} imageSrc="data:x" buttonText="换" />)
    expect(Array.from(document.querySelector(".ak-code-row")!.children).map((c) => c.className)).toEqual(["ak-input ak-code-input", "ak-code-img", "ak-code-btn"])
  })

  it("CSS: nowrap, bottom aligned, 40px controls", () => {
    const css = CODE_ROW_CSS.replace(/\s+/g, " ")
    expect(css).toMatch(/\.ak-code-row\{[^}]*flex-wrap:nowrap;align-items:flex-end/)
    expect(css).toMatch(/\.ak-code-input\{[^}]*height:var\(--ak-control-height,40px\)/)
    expect(css).toMatch(/\.ak-code-btn\{[^}]*flex:0 0 auto;min-width:96px;height:var\(--ak-control-height,40px\)[^}]*white-space:nowrap/)
  })
})
