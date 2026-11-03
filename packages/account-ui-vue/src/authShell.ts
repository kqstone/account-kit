import { defineComponent, h, type PropType, type StyleValue } from "vue"
import { ensureAccountStyle } from "./client"
import { detectNative, ensureShellStyle } from "./shellStyle"

let seq = 0

/**
 * Full-screen auth layout: fixed brand header, card with fixed title/footer and the only
 * scrollable body, fixed web copyright. DOM/classes match the React AuthShell.
 * Slots: default (scroll body), logo, lang, footer, copyright, extra, title, subtitle, brand.
 */
export const AuthShell = defineComponent({
  name: "AuthShell",
  props: {
    brandName: { type: String, default: undefined },
    brandSubtitle: { type: String, default: undefined },
    title: { type: String, default: undefined },
    subtitle: { type: String, default: undefined },
    copyright: { type: String, default: undefined },
    showCopyright: { type: Boolean, default: undefined },
    showLanguageSwitch: { type: Boolean, default: undefined },
    /** Defaults to detectNative() (Capacitor native platform). */
    native: { type: Boolean, default: undefined },
    variant: { type: String as PropType<"user" | "admin">, default: "user" },
    /** Extra attributes for <header>, e.g. { "data-tauri-drag-region": "" }. */
    headerAttrs: { type: Object as PropType<Record<string, unknown>>, default: null },
    cardClass: { type: [String, Array, Object] as PropType<string | string[] | Record<string, boolean>>, default: undefined },
    cardStyle: { type: [String, Object, Array] as PropType<StyleValue>, default: undefined },
    /** Bound via `@brand-click`; makes the brand block a keyboard-accessible button. */
    onBrandClick: { type: Function as PropType<() => void>, default: undefined },
  },
  setup(props, { slots }) {
    ensureShellStyle()
    return () => {
      const native = props.native ?? detectNative()
      const showLang = (props.showLanguageSwitch ?? !native) && Boolean(slots.lang)
      const hasCopy = props.copyright != null || Boolean(slots.copyright)
      const showCopy = (props.showCopyright ?? !native) && hasCopy
      const clickable = typeof props.onBrandClick === "function"
      const hasTitle = props.title != null || Boolean(slots.title)
      const hasSubtitle = props.subtitle != null || Boolean(slots.subtitle)
      const hasBrand = Boolean(slots.logo || slots.brand) || props.brandName != null || props.brandSubtitle != null
      const fire = () => props.onBrandClick?.()
      const header = props.headerAttrs ?? {}
      return h(
        "div",
        { class: ["ak-shell", `ak-shell--${props.variant}`, native ? "is-native" : "is-web", showCopy ? "has-copyright" : "no-copyright"] },
        [
          showLang ? h("div", { class: "ak-shell-lang" }, slots.lang?.()) : null,
          h("header", { ...header, class: ["ak-shell-header", header.class as string | undefined] }, [
            hasBrand
              ? h(
                  "div",
                  {
                    class: ["ak-shell-brand", clickable ? "is-clickable" : null],
                    role: clickable ? "button" : undefined,
                    tabindex: clickable ? 0 : undefined,
                    onClick: clickable ? fire : undefined,
                    onKeydown: clickable
                      ? (event: KeyboardEvent) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault()
                            fire()
                          }
                        }
                      : undefined,
                  },
                  slots.brand
                    ? slots.brand()
                    : [
                        slots.logo ? h("div", { class: "ak-shell-logo" }, slots.logo()) : null,
                        props.brandName != null ? h("div", { class: "ak-shell-brand-name" }, props.brandName) : null,
                        props.brandSubtitle != null ? h("div", { class: "ak-shell-brand-subtitle" }, props.brandSubtitle) : null,
                      ],
                )
              : null,
          ]),
          h("main", { class: "ak-shell-main" }, [
            h("div", { class: ["ak-shell-card", props.cardClass], style: props.cardStyle }, [
              hasTitle || hasSubtitle
                ? h("div", { class: "ak-shell-card-header" }, [
                    hasTitle ? h("h1", { class: "ak-shell-title" }, slots.title ? slots.title() : props.title) : null,
                    hasSubtitle ? h("p", { class: "ak-shell-subtitle" }, slots.subtitle ? slots.subtitle() : props.subtitle) : null,
                  ])
                : null,
              h("div", { class: "ak-shell-body" }, slots.default?.()),
              slots.footer ? h("div", { class: "ak-shell-card-footer" }, slots.footer()) : null,
            ]),
          ]),
          showCopy ? h("footer", { class: "ak-shell-footer" }, slots.copyright ? slots.copyright() : props.copyright) : null,
          slots.extra?.(),
        ],
      )
    }
  },
})

/** Code/captcha row: label outside, input + optional image + button on one 40px line. Same DOM as React. */
export const CodeInputRow = defineComponent({
  name: "CodeInputRow",
  props: {
    label: { type: String, default: undefined },
    modelValue: { type: String, default: "" },
    placeholder: { type: String, default: undefined },
    maxlength: { type: Number, default: undefined },
    inputmode: { type: String as PropType<"numeric" | "text" | "decimal" | "tel" | "email" | "url" | "search" | "none">, default: undefined },
    autocomplete: { type: String, default: "off" },
    name: { type: String, default: undefined },
    imageSrc: { type: String, default: "" },
    imageAlt: { type: String, default: "captcha" },
    buttonText: { type: String, default: "" },
    buttonDisabled: { type: Boolean, default: false },
    hideButton: { type: Boolean, default: false },
  },
  emits: ["update:modelValue", "button-click", "image-click"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
    const id = `ak-code-${++seq}`
    return () =>
      h("div", { class: "ak-field ak-code-field" }, [
        props.label != null || slots.label ? h("label", { class: "ak-field-label", for: id }, slots.label ? slots.label() : props.label) : null,
        h("div", { class: "ak-code-row ak-row" }, [
          h("input", {
            id,
            class: "ak-input ak-code-input",
            name: props.name,
            value: props.modelValue,
            maxlength: props.maxlength,
            inputmode: props.inputmode,
            autocomplete: props.autocomplete,
            placeholder: props.placeholder,
            onInput: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).value),
          }),
          props.imageSrc ? h("img", { class: "ak-code-img", src: props.imageSrc, alt: props.imageAlt, onClick: () => emit("image-click") }) : null,
          props.hideButton
            ? null
            : h("button", { type: "button", class: "ak-code-btn", disabled: props.buttonDisabled, onClick: () => emit("button-click") }, slots.button ? slots.button() : props.buttonText),
        ]),
        slots.default?.(),
      ])
  },
})
