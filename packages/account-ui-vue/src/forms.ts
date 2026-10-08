import { computed, defineComponent, h, onMounted, ref, type PropType } from "vue"
import { AccountApiError, ensureAccountStyle, type AccountClient } from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveFormLabels, type FormLabels } from "./labels"
import { formatError, interpolate, textOf, type DeepPartial } from "./utils"

function field(label: string, input: ReturnType<typeof h>) {
  return h("label", [label, input])
}

export const LoginForm = defineComponent({
  name: "LoginForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    deviceName: { type: String, default: "" },
    initialUsername: { type: String, default: "" },
    initialPassword: { type: String, default: "" },
    trustedDeviceToken: { type: [String, Function] as PropType<string | ((username: string) => string)>, default: "" },
    beforeSubmit: { type: Function as PropType<() => boolean | Promise<boolean | void>>, default: null },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
  },
  emits: ["success", "mfa"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveFormLabels(locale.value, props.labels, messages))
    const username = ref(props.initialUsername || "")
    const password = ref(props.initialPassword || "")
    const error = ref("")
    const busy = ref(false)
    const force = ref(false)
    const captchaNeeded = ref(false)
    const captchaId = ref("")
    const captchaImage = ref("")
    const captchaCode = ref("")

    async function loadCaptcha() {
      captchaId.value = ""
      captchaImage.value = ""
      captchaCode.value = ""
      if (typeof props.client.captcha !== "function") return
      try {
        const data = await props.client.captcha()
        captchaId.value = data.captcha_id || ""
        captchaImage.value = data.image_base64 ? `data:image/png;base64,${data.image_base64}` : ""
      } catch {
        error.value = L.value.captchaLoadFailed
      }
    }

    async function submit() {
      error.value = ""
      if (captchaNeeded.value && (!captchaId.value || !captchaCode.value.trim())) {
        error.value = L.value.captchaEnter
        return
      }
      busy.value = true
      const usedCaptcha = captchaNeeded.value
      try {
        if (props.beforeSubmit) {
          const ok = await props.beforeSubmit()
          if (ok === false) return
        }
        const name = username.value.trim()
        const trusted =
          typeof props.trustedDeviceToken === "function" ? props.trustedDeviceToken(name) : props.trustedDeviceToken
        const token = await props.client.login(name, password.value, {
          force: force.value,
          deviceName: props.deviceName || undefined,
          trustedDeviceToken: trusted || undefined,
          captchaId: usedCaptcha ? captchaId.value : undefined,
          captchaCode: usedCaptcha ? captchaCode.value.trim() : undefined,
        })
        captchaNeeded.value = false
        emit("success", token.access_token, { username: username.value, password: password.value, tokens: token })
      } catch (err) {
        const body = err instanceof AccountApiError ? err.body : null
        const detail =
          body && typeof body === "object" && "detail" in body
            ? (body as {
                detail?: { code?: string; device_name?: string; challenge_token?: string; captcha_required?: boolean }
              }).detail
            : null
        const status = err instanceof AccountApiError ? err.status : 0
        const code = detail && typeof detail === "object" ? detail.code : undefined
        if (usedCaptcha) captchaNeeded.value = false
        if (
          status === 428 ||
          code === "CAPTCHA_REQUIRED" ||
          code === "CAPTCHA_INVALID" ||
          (detail && typeof detail === "object" && detail.captcha_required)
        ) {
          captchaNeeded.value = true
          await loadCaptcha()
          error.value =
            code === "CAPTCHA_INVALID"
              ? L.value.captchaInvalid
              : status === 428 || code === "CAPTCHA_REQUIRED"
                ? L.value.captchaEnter
                : formatError(err, L.value, locale.value)
          return
        }
        if (err instanceof AccountApiError && err.status === 401 && detail?.code === "MFA_REQUIRED" && detail.challenge_token) {
          emit("mfa", { ...detail, username: username.value, password: password.value, force: force.value })
          return
        }
        if (err instanceof AccountApiError && err.status === 409 && detail?.code === "ALREADY_LOGGED_IN") {
          force.value = true
          error.value = interpolate(L.value.alreadyLoggedIn, {
            device: (detail && typeof detail === "object" && detail.device_name) || L.value.errors.UNKNOWN_DEVICE,
          })
          return
        }
        error.value = formatError(err, L.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    return () =>
      h(
        "form",
        {
          class: "ak-form",
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          field(
            L.value.username,
            h("input", {
              value: username.value,
              autocomplete: "username",
              onInput: (event: Event) => {
                username.value = textOf(event)
              },
            }),
          ),
          field(
            L.value.password,
            h("input", {
              type: "password",
              value: password.value,
              autocomplete: "current-password",
              onInput: (event: Event) => {
                password.value = textOf(event)
              },
            }),
          ),
          captchaNeeded.value
            ? field(
                L.value.captcha,
                h("span", { class: "ak-row" }, [
                  h("input", {
                    value: captchaCode.value,
                    autocomplete: "off",
                    placeholder: L.value.captchaPlaceholder,
                    onInput: (event: Event) => {
                      captchaCode.value = textOf(event)
                    },
                  }),
                  captchaImage.value
                    ? h("img", {
                        src: captchaImage.value,
                        alt: "captcha",
                        style: "height:36px;cursor:pointer",
                        onClick: () => void loadCaptcha(),
                      })
                    : null,
                  h("button", { type: "button", onClick: () => void loadCaptcha() }, L.value.captchaRefresh),
                ]),
              )
            : null,
          slots.default?.(),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? L.value.loggingIn : force.value ? L.value.forceLogin : L.value.login),
        ],
      )
  },
})

export const RegisterForm = defineComponent({
  name: "RegisterForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    extraPayload: { type: Object as PropType<Record<string, unknown>>, default: () => ({}) },
    beforeSubmit: { type: Function as PropType<() => boolean | Promise<boolean | void>>, default: null },
  },
  emits: ["success"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveFormLabels(locale.value, props.labels, messages))
    const username = ref("")
    const email = ref("")
    const password = ref("")
    const fullName = ref("")
    const institution = ref("")
    const gender = ref("")
    const birth = ref("")
    const code = ref("")
    const role = ref("")
    const roles = ref<Array<{ code: string; name: string }>>([])
    const error = ref("")
    const busy = ref(false)
    const sending = ref(false)

    onMounted(async () => {
      try {
        roles.value = await props.client.roles()
      } catch {
        roles.value = []
      }
    })

    async function sendCode() {
      error.value = ""
      sending.value = true
      try {
        await props.client.sendCode(email.value.trim(), "register", locale.value)
      } catch (err) {
        error.value = formatError(err, L.value, locale.value)
      } finally {
        sending.value = false
      }
    }

    async function submit() {
      error.value = ""
      busy.value = true
      try {
        if (props.beforeSubmit) {
          const ok = await props.beforeSubmit()
          if (ok === false) return
        }
        const user = await props.client.register({
          username: username.value.trim(),
          email: email.value.trim(),
          password: password.value,
          code: code.value.trim(),
          full_name: fullName.value.trim() || undefined,
          institution: institution.value.trim() || undefined,
          gender: gender.value || undefined,
          birth_year_month: birth.value || undefined,
          role: role.value || undefined,
          ...(props.extraPayload || {}),
        })
        emit("success", user)
      } catch (err) {
        error.value = formatError(err, L.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    return () =>
      h(
        "form",
        {
          class: "ak-form",
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          field(L.value.username, h("input", { value: username.value, autocomplete: "username", onInput: (event: Event) => { username.value = textOf(event) } })),
          field(L.value.email, h("input", { type: "email", value: email.value, autocomplete: "email", onInput: (event: Event) => { email.value = textOf(event) } })),
          field(L.value.password, h("input", { type: "password", value: password.value, autocomplete: "new-password", onInput: (event: Event) => { password.value = textOf(event) } })),
          field(L.value.fullNameOptional, h("input", { value: fullName.value, autocomplete: "name", onInput: (event: Event) => { fullName.value = textOf(event) } })),
          field(L.value.institutionOptional, h("input", { value: institution.value, onInput: (event: Event) => { institution.value = textOf(event) } })),
          field(
            L.value.genderOptional,
            h("select", { value: gender.value, onChange: (event: Event) => { gender.value = textOf(event) } }, [
              h("option", { value: "" }, L.value.genderUnspecified),
              h("option", { value: "male" }, L.value.genderMale),
              h("option", { value: "female" }, L.value.genderFemale),
            ]),
          ),
          field(L.value.birthOptional, h("input", { type: "month", value: birth.value, onInput: (event: Event) => { birth.value = textOf(event) } })),
          h("div", { class: "ak-row" }, [
            field(L.value.code, h("input", { value: code.value, maxlength: 6, inputmode: "numeric", onInput: (event: Event) => { code.value = textOf(event) } })),
            h("button", { type: "button", disabled: sending.value, onClick: () => void sendCode() }, sending.value ? L.value.sending : L.value.sendCode),
          ]),
          roles.value.length
            ? field(
                L.value.role,
                h("select", { value: role.value, onChange: (event: Event) => { role.value = textOf(event) } }, [
                  h("option", { value: "" }, L.value.roleDefault),
                  ...roles.value.map((item) => h("option", { value: item.code }, item.name)),
                ]),
              )
            : null,
          slots.default?.(),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? L.value.submitting : L.value.register),
        ],
      )
  },
})

export const ResetPasswordForm = defineComponent({
  name: "ResetPasswordForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
  },
  emits: ["success"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveFormLabels(locale.value, props.labels, messages))
    const email = ref("")
    const code = ref("")
    const password = ref("")
    const error = ref("")
    const busy = ref(false)
    const sending = ref(false)

    async function sendCode() {
      error.value = ""
      sending.value = true
      try {
        await props.client.sendCode(email.value.trim(), "reset_password", locale.value)
      } catch (err) {
        error.value = formatError(err, L.value, locale.value)
      } finally {
        sending.value = false
      }
    }

    async function submit() {
      error.value = ""
      busy.value = true
      try {
        await props.client.resetPassword(email.value.trim(), code.value.trim(), password.value)
        emit("success")
      } catch (err) {
        error.value = formatError(err, L.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    return () =>
      h(
        "form",
        {
          class: "ak-form",
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          field(L.value.email, h("input", { type: "email", value: email.value, autocomplete: "email", onInput: (event: Event) => { email.value = textOf(event) } })),
          h("div", { class: "ak-row" }, [
            field(L.value.code, h("input", { value: code.value, maxlength: 6, inputmode: "numeric", onInput: (event: Event) => { code.value = textOf(event) } })),
            h("button", { type: "button", disabled: sending.value, onClick: () => void sendCode() }, sending.value ? L.value.sending : L.value.sendCode),
          ]),
          field(L.value.newPassword, h("input", { type: "password", value: password.value, autocomplete: "new-password", onInput: (event: Event) => { password.value = textOf(event) } })),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? L.value.submitting : L.value.resetPassword),
        ],
      )
  },
})
