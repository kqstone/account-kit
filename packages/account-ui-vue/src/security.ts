import { defineComponent, h, onBeforeUnmount, onMounted, ref, type PropType } from "vue"
import { ensureAccountStyle, type AccountClient, type AccountUser, type CodeSentResult } from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveProfileLabels, type ProfileLabels } from "./labels"
import { interpolate, messageOf, textOf, type DeepPartial } from "./utils"

/** Split a single "2FA code" input into a TOTP code or a recovery code. */
export function splitSecondFactor(value: string) {
  const cleaned = value.trim()
  if (!cleaned) return { code: "", recoveryCode: "" }
  return /^\d[\d\s]*$/.test(cleaned) ? { code: cleaned.replace(/\s+/g, ""), recoveryCode: "" } : { code: "", recoveryCode: cleaned }
}

function useCountdown() {
  const left = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  function start(seconds: number) {
    left.value = Math.max(0, Math.floor(seconds))
    if (timer) clearInterval(timer)
    timer = setInterval(() => {
      left.value -= 1
      if (left.value <= 0 && timer) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  }
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
  })
  return { left, start }
}

/** Image captcha (``client.captcha()``): click the image to reload. Emits ``change`` with the captcha id. */
export const CaptchaImage = defineComponent({
  name: "CaptchaImage",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    modelValue: { type: String, default: "" },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
  },
  emits: ["update:modelValue", "change", "error"],
  setup(props, { emit, expose }) {
    ensureAccountStyle()
    const image = ref("")
    const error = ref("")
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveProfileLabels(locale.value, props.labels, messages)

    async function reload() {
      error.value = ""
      emit("update:modelValue", "")
      try {
        const data = await props.client.captcha()
        image.value = data.image_base64 ? `data:image/png;base64,${data.image_base64}` : ""
        emit("change", data.captcha_id || "")
      } catch (e) {
        image.value = ""
        error.value = L().captchaLoadFailed
        emit("error", e)
      }
    }
    onMounted(() => void reload())
    expose({ reload })

    return () => {
      const labels = L()
      return h("label", { class: "ak-field" }, [
        labels.captcha,
        h("span", { class: "ak-row" }, [
          h("input", {
            class: "ak-input",
            value: props.modelValue,
            autocomplete: "off",
            placeholder: labels.captchaPlaceholder,
            onInput: (event: Event) => emit("update:modelValue", textOf(event)),
          }),
          image.value
            ? h("img", { class: "ak-captcha-img", src: image.value, alt: "captcha", title: labels.captchaRefresh, onClick: () => void reload() })
            : h("button", { type: "button", class: "ak-link", onClick: () => void reload() }, labels.captchaRefresh),
        ]),
        error.value ? h("p", { class: "ak-error" }, error.value) : null,
      ])
    }
  },
})

/** Verified email change: code to the new address (POST /me/email/send-code), then POST /me/email. */
export const ChangeEmailForm = defineComponent({
  name: "ChangeEmailForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    user: { type: Object as PropType<AccountUser | null>, default: null },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
    requirePassword: { type: Boolean, default: true },
    className: { type: String, default: "" },
  },
  emits: ["changed", "error"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const newEmail = ref("")
    const code = ref("")
    const password = ref("")
    const error = ref("")
    const info = ref("")
    const busy = ref(false)
    const sending = ref(false)
    const { left, start } = useCountdown()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveProfileLabels(locale.value, props.labels, messages)

    async function sendCode() {
      error.value = ""
      info.value = ""
      sending.value = true
      try {
        const sent: CodeSentResult = await props.client.sendChangeEmailCode(props.token, newEmail.value.trim(), { language: locale.value })
        info.value = interpolate(L().codeSentTo, { email: sent.email || newEmail.value.trim() })
        start(sent.cooldown || 60)
      } catch (e) {
        error.value = messageOf(e, L().error)
        emit("error", e)
      } finally {
        sending.value = false
      }
    }

    async function submit() {
      error.value = ""
      info.value = ""
      busy.value = true
      try {
        const user = await props.client.changeEmail(props.token, newEmail.value.trim(), code.value.trim(), password.value || undefined)
        info.value = L().emailChanged
        code.value = ""
        password.value = ""
        emit("changed", user)
      } catch (e) {
        error.value = messageOf(e, L().error)
        emit("error", e)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L()
      return h(
        "form",
        {
          class: ["ak-form", props.className].filter(Boolean).join(" "),
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          props.user?.email ? h("p", { class: "ak-muted" }, `${labels.currentEmail}: ${props.user.email}`) : null,
          h("label", [labels.newEmail, h("input", { type: "email", value: newEmail.value, autocomplete: "email", onInput: (e: Event) => { newEmail.value = textOf(e) } })]),
          h("div", { class: "ak-row" }, [
            h("input", { class: "ak-input", value: code.value, maxlength: 6, inputmode: "numeric", placeholder: labels.emailCodePlaceholder, onInput: (e: Event) => { code.value = textOf(e) } }),
            h(
              "button",
              { type: "button", disabled: sending.value || left.value > 0 || !newEmail.value.trim(), onClick: () => void sendCode() },
              sending.value ? labels.sending : left.value > 0 ? interpolate(labels.resendIn, { s: left.value }) : labels.sendCode,
            ),
          ]),
          props.requirePassword
            ? h("label", [labels.oldPassword, h("input", { type: "password", value: password.value, autocomplete: "current-password", onInput: (e: Event) => { password.value = textOf(e) } })])
            : null,
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          info.value ? h("p", { class: "ak-success" }, info.value) : null,
          h("button", { type: "submit", disabled: busy.value || !code.value.trim() }, busy.value ? labels.saving : labels.confirmChangeEmail),
        ],
      )
    }
  },
})

/** Self-service account deletion (server ``self_delete_enabled``). */
export const DeleteAccountForm = defineComponent({
  name: "DeleteAccountForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
    /** Show the 2FA input (pass ``TwoFactorStatus.enabled``). */
    twoFactorEnabled: { type: Boolean, default: false },
    /** Offer an emailed code instead of TOTP (server ``two_factor_email_enabled``). */
    emailCodeAvailable: { type: Boolean, default: false },
    className: { type: String, default: "" },
  },
  emits: ["deleted", "error"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const password = ref("")
    const factor = ref("")
    const emailCode = ref("")
    const ack = ref(false)
    const error = ref("")
    const busy = ref(false)
    const sending = ref(false)
    const { left, start } = useCountdown()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveProfileLabels(locale.value, props.labels, messages)

    async function sendEmail() {
      error.value = ""
      sending.value = true
      try {
        const sent = await props.client.sendDeleteAccountEmailCode(props.token, locale.value)
        start(sent.cooldown || 60)
      } catch (e) {
        error.value = messageOf(e, L().error)
      } finally {
        sending.value = false
      }
    }

    async function submit() {
      error.value = ""
      busy.value = true
      try {
        const result = await props.client.deleteAccount(props.token, {
          password: password.value,
          ...splitSecondFactor(factor.value),
          emailCode: emailCode.value.trim() || undefined,
        })
        emit("deleted", result)
      } catch (e) {
        error.value = messageOf(e, L().error)
        emit("error", e)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L()
      return h(
        "form",
        {
          class: ["ak-form", "ak-danger-zone", props.className].filter(Boolean).join(" "),
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          h("h3", { style: "margin:0;font-size:15px" }, labels.deleteAccount),
          h("p", { class: "ak-warn" }, labels.deleteAccountHint),
          h("label", [labels.oldPassword, h("input", { type: "password", value: password.value, autocomplete: "current-password", onInput: (e: Event) => { password.value = textOf(e) } })]),
          props.twoFactorEnabled
            ? h("label", [labels.twoFactorCode, h("input", { value: factor.value, autocomplete: "one-time-code", onInput: (e: Event) => { factor.value = textOf(e) } })])
            : null,
          props.twoFactorEnabled && props.emailCodeAvailable
            ? h("div", { class: "ak-row" }, [
                h("input", { class: "ak-input", value: emailCode.value, maxlength: 6, placeholder: labels.emailCodePlaceholder, onInput: (e: Event) => { emailCode.value = textOf(e) } }),
                h(
                  "button",
                  { type: "button", disabled: sending.value || left.value > 0, onClick: () => void sendEmail() },
                  sending.value ? labels.sending : left.value > 0 ? interpolate(labels.resendIn, { s: left.value }) : labels.sendCode,
                ),
              ])
            : null,
          h("label", { class: "ak-check" }, [
            h("input", { type: "checkbox", checked: ack.value, onChange: (e: Event) => { ack.value = (e.target as HTMLInputElement).checked } }),
            labels.deleteAccountTyped,
          ]),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", class: "ak-btn ak-btn-danger", disabled: busy.value || !ack.value || !password.value }, labels.deleteAccountConfirm),
        ],
      )
    }
  },
})

/** Calls the kit logout (revokes the session and refresh token), then emits ``done`` even on network errors. */
export const LogoutButton = defineComponent({
  name: "LogoutButton",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, default: "" },
    refreshToken: { type: String, default: "" },
    allDevices: { type: Boolean, default: false },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
    className: { type: String, default: "" },
  },
  emits: ["done"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
    const busy = ref(false)
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveProfileLabels(locale.value, props.labels, messages)
    async function run() {
      busy.value = true
      let error: unknown = null
      try {
        await props.client.logout(props.token || null, { refreshToken: props.refreshToken || null, allDevices: props.allDevices })
      } catch (e) {
        error = e
      } finally {
        busy.value = false
        emit("done", error)
      }
    }
    return () => {
      const labels = L()
      return h(
        "button",
        { type: "button", class: ["ak-btn", "ak-btn-outline", props.className].filter(Boolean).join(" "), disabled: busy.value, onClick: () => void run() },
        slots.default?.() || (busy.value ? labels.loggingOut : props.allDevices ? labels.logoutAll : labels.logout),
      )
    }
  },
})
