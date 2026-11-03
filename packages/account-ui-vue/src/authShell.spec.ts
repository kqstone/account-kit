import { mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import { h } from "vue"
import { AuthShell, CodeInputRow } from "./authShell"
import { CODE_ROW_CSS, detectNative, SHELL_CSS, systemLocale } from "./shellStyle"

function selectors(css: string): string[] {
  const out: string[] = []
  const stripped = css.replace(/@media[^{]*\{/g, "")
  for (const m of stripped.matchAll(/([^{}]+)\{[^{}]*\}/g)) out.push(...m[1].split(",").map((s) => s.trim()).filter(Boolean))
  return out
}

afterEach(() => {
  document.body.innerHTML = ""
  delete (globalThis as { Capacitor?: unknown }).Capacitor
})

describe("AuthShell (vue)", () => {
  it("renders brand, header, scroll body, card footer, copyright, lang and extra in place", () => {
    const w = mount(AuthShell, {
      props: { brandName: "Brand", brandSubtitle: "Sub", title: "登录", subtitle: "欢迎", copyright: "© 2026", native: false },
      slots: {
        logo: () => h("i", { "data-testid": "logo" }),
        lang: () => h("span", { "data-testid": "lang" }),
        footer: () => h("a", { href: "#r" }, "注册"),
        extra: () => h("div", { "data-testid": "modal" }),
        default: () => h("form", { "data-testid": "form" }),
      },
    })
    const shell = w.element as HTMLElement
    expect(shell.classList.contains("ak-shell")).toBe(true)
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
  })

  it("hides language switch and copyright when native", () => {
    const w = mount(AuthShell, { props: { native: true, copyright: "©", brandName: "B" }, slots: { lang: () => h("span") } })
    expect(w.classes()).toContain("is-native")
    expect(w.find(".ak-shell-lang").exists()).toBe(false)
    expect(w.find(".ak-shell-footer").exists()).toBe(false)
  })

  it("defaults native from Capacitor and allows explicit overrides", () => {
    ;(globalThis as { Capacitor?: unknown }).Capacitor = { isNativePlatform: () => true }
    expect(detectNative()).toBe(true)
    const w = mount(AuthShell, { props: { copyright: "©", showCopyright: true }, slots: { lang: () => h("span") } })
    expect(w.find(".ak-shell-lang").exists()).toBe(false)
    expect(w.find(".ak-shell-footer").exists()).toBe(true)
  })

  it("only the body scrolls: CSS rules", () => {
    const css = (CODE_ROW_CSS + SHELL_CSS).replace(/\s+/g, " ")
    expect(css).toMatch(/\.ak-shell\{[^}]*height:100dvh[^}]*overflow:hidden/)
    expect(css).toMatch(/\.ak-shell-body\{[^}]*min-height:0;overflow-y:auto[^}]*overscroll-behavior:contain/)
    expect(css).toMatch(/\.ak-shell-card\{[^}]*max-height:100%[^}]*overflow:hidden/)
    for (const v of ["--ak-shell-bg", "--ak-shell-primary", "--ak-shell-card-bg", "--ak-shell-card-radius", "--ak-control-height"]) expect(css).toContain(`var(${v}`)
  })

  it("does not style slot controls (el-form): selectors scoped, no bare input/button", () => {
    for (const sel of selectors(CODE_ROW_CSS + SHELL_CSS)) {
      expect(sel.startsWith(".ak-"), sel).toBe(true)
      const parts = sel.split(/\s+|>/).filter(Boolean)
      parts.forEach((part, i) => {
        if (!/^(input|button|select|textarea|label|a|form)\b/.test(part)) return
        expect(parts.slice(0, i).some((p) => p === ".ak-form" || p === ".ak-shell-card-footer"), sel).toBe(true)
      })
    }
    const w = mount(AuthShell, {
      props: { native: false },
      slots: { default: () => h("form", { class: "el-form" }, [h("input", { class: "el-input__inner" }), h("button", { class: "el-button" }, "x")]) },
      attachTo: document.body,
    })
    const el = w.find(".el-input__inner").element as HTMLInputElement
    expect(getComputedStyle(el).height).not.toBe("40px")
    w.unmount()
  })

  it("brand click via mouse and keyboard; headerAttrs pass through", async () => {
    const onBrand = vi.fn()
    const w = mount(AuthShell, { props: { brandName: "B", native: false, onBrandClick: onBrand, headerAttrs: { "data-tauri-drag-region": "" } } })
    const brand = w.find(".ak-shell-brand")
    expect(brand.attributes("role")).toBe("button")
    expect(brand.attributes("tabindex")).toBe("0")
    await brand.trigger("click")
    await brand.trigger("keydown", { key: "Enter" })
    await brand.trigger("keydown", { key: " " })
    await brand.trigger("keydown", { key: "a" })
    expect(onBrand).toHaveBeenCalledTimes(3)
    expect(w.find("header.ak-shell-header").attributes()).toHaveProperty("data-tauri-drag-region")
  })

  it("systemLocale returns a language", () => {
    expect(systemLocale().length).toBeGreaterThan(0)
  })
})

describe("CodeInputRow (vue)", () => {
  it("label outside the row, keeps .ak-row, emits", async () => {
    const w = mount(CodeInputRow, { props: { label: "验证码", modelValue: "", buttonText: "发送", maxlength: 6 } })
    const field = w.element as HTMLElement
    expect(Array.from(field.children).map((c) => c.tagName + "." + c.className)).toEqual(["LABEL.ak-field-label", "DIV.ak-code-row ak-row"])
    expect(Array.from(field.querySelector(".ak-code-row")!.children).map((c) => c.tagName)).toEqual(["INPUT", "BUTTON"])
    expect(w.find("label").attributes("for")).toBe(w.find("input").attributes("id"))
    await w.find("input").setValue("123")
    expect(w.emitted("update:modelValue")![0]).toEqual(["123"])
    await w.find("button").trigger("click")
    expect(w.emitted("button-click")).toHaveLength(1)
  })

  it("captcha image between input and button", () => {
    const w = mount(CodeInputRow, { props: { modelValue: "", imageSrc: "data:x", buttonText: "换" } })
    expect(Array.from(w.find(".ak-code-row").element.children).map((c) => c.className)).toEqual(["ak-input ak-code-input", "ak-code-img", "ak-code-btn"])
  })

  it("CSS: nowrap, bottom aligned, 40px", () => {
    const css = CODE_ROW_CSS.replace(/\s+/g, " ")
    expect(css).toMatch(/\.ak-code-row\{[^}]*flex-wrap:nowrap;align-items:flex-end/)
    expect(css).toMatch(/\.ak-code-btn\{[^}]*min-width:96px;height:var\(--ak-control-height,40px\)[^}]*white-space:nowrap/)
  })
})
