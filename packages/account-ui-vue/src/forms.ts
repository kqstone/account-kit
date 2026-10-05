import { defineComponent, h, onMounted, ref, type PropType } from "vue"
import { AccountApiError, ensureAccountStyle, type AccountClient } from "./client"

function textOf(event: Event) {
  return (event.target as HTMLInputElement).value
}

function messageOf(error: unknown) {
  if (error instanceof AccountApiError) return error.message || "请求失败"
  if (error instanceof Error) return error.message
  return "请求失败"
}

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
  },
  emits: ["success", "mfa"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
    const username = ref(props.initialUsername || "")
    const password = ref(props.initialPassword || "")
    const error = ref("")
    const busy = ref(false)
    const force = ref(false)
    // Image captcha (428 CAPTCHA_REQUIRED after repeated failures, when the host enables it)
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
        error.value = "验证码加载失败，请点击换一张"
      }
    }

    async function submit() {
      error.value = ""
      if (captchaNeeded.value && (!captchaId.value || !captchaCode.value.trim())) {
        error.value = "请输入图形验证码"
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
        emit("success", token.access_token, { username: username.value, password: password.value })
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
        // A captcha is single-use: any reply after sending one needs a fresh image.
        if (usedCaptcha) captchaNeeded.value = false
        if (status === 428 || code === "CAPTCHA_REQUIRED" || code === "CAPTCHA_INVALID" || (detail && typeof detail === "object" && detail.captcha_required)) {
          captchaNeeded.value = true
          await loadCaptcha()
          error.value =
            code === "CAPTCHA_INVALID"
              ? "图形验证码错误或已失效，请重试"
              : status === 428 || code === "CAPTCHA_REQUIRED"
                ? "请输入图形验证码"
                : messageOf(err)
          return
        }
        if (err instanceof AccountApiError && err.status === 401 && detail?.code === "MFA_REQUIRED" && detail.challenge_token) {
          emit("mfa", { ...detail, username: username.value, password: password.value, force: force.value })
          return
        }
        if (err instanceof AccountApiError && err.status === 409 && detail?.code === "ALREADY_LOGGED_IN") {
          force.value = true
          error.value = `该账号已在${detail.device_name || "其他设备"}登录，再次提交将挤掉该设备`
          return
        }
        error.value = messageOf(err)
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
          field("用户名", h("input", { value: username.value, autocomplete: "username", onInput: (event: Event) => { username.value = textOf(event) } })),
          field("密码", h("input", { type: "password", value: password.value, autocomplete: "current-password", onInput: (event: Event) => { password.value = textOf(event) } })),
          captchaNeeded.value
            ? field(
                "图形验证码",
                h("span", { class: "ak-row" }, [
                  h("input", {
                    value: captchaCode.value,
                    autocomplete: "off",
                    placeholder: "输入图中字符",
                    onInput: (event: Event) => {
                      captchaCode.value = textOf(event)
                    },
                  }),
                  captchaImage.value
                    ? h("img", { src: captchaImage.value, alt: "captcha", style: "height:36px;cursor:pointer", onClick: () => void loadCaptcha() })
                    : null,
                  h("button", { type: "button", onClick: () => void loadCaptcha() }, "换一张"),
                ]),
              )
            : null,
          slots.default?.(),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? "登录中…" : force.value ? "强制登录" : "登录"),
        ],
      )
  },
})

export const RegisterForm = defineComponent({
  name: "RegisterForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    language: { type: String, default: "zh" },
    extraPayload: { type: Object as PropType<Record<string, unknown>>, default: () => ({}) },
    beforeSubmit: { type: Function as PropType<() => boolean | Promise<boolean | void>>, default: null },
  },
  emits: ["success"],
  setup(props, { emit, slots }) {
    ensureAccountStyle()
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
        await props.client.sendCode(email.value.trim(), "register", props.language)
      } catch (err) {
        error.value = messageOf(err)
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
        error.value = messageOf(err)
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
          field("用户名", h("input", { value: username.value, autocomplete: "username", onInput: (event: Event) => { username.value = textOf(event) } })),
          field("邮箱", h("input", { type: "email", value: email.value, autocomplete: "email", onInput: (event: Event) => { email.value = textOf(event) } })),
          field("密码", h("input", { type: "password", value: password.value, autocomplete: "new-password", onInput: (event: Event) => { password.value = textOf(event) } })),
          field("姓名（可选）", h("input", { value: fullName.value, autocomplete: "name", onInput: (event: Event) => { fullName.value = textOf(event) } })),
          field("机构（可选）", h("input", { value: institution.value, onInput: (event: Event) => { institution.value = textOf(event) } })),
          field(
            "性别（可选）",
            h(
              "select",
              { value: gender.value, onChange: (event: Event) => { gender.value = textOf(event) } },
              [h("option", { value: "" }, "未指定"), h("option", { value: "male" }, "男"), h("option", { value: "female" }, "女")],
            ),
          ),
          field("出生年月（可选）", h("input", { type: "month", value: birth.value, onInput: (event: Event) => { birth.value = textOf(event) } })),
          h("div", { class: "ak-row" }, [
            field("验证码", h("input", { value: code.value, maxlength: 6, inputmode: "numeric", onInput: (event: Event) => { code.value = textOf(event) } })),
            h("button", { type: "button", disabled: sending.value, onClick: () => void sendCode() }, sending.value ? "发送中…" : "发送验证码"),
          ]),
          roles.value.length
            ? field(
                "角色",
                h(
                  "select",
                  { value: role.value, onChange: (event: Event) => { role.value = textOf(event) } },
                  [h("option", { value: "" }, "默认"), ...roles.value.map((item) => h("option", { value: item.code }, item.name))],
                ),
              )
            : null,
          slots.default?.(),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? "提交中…" : "注册"),
        ],
      )
  },
})

export const ResetPasswordForm = defineComponent({
  name: "ResetPasswordForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    language: { type: String, default: "zh" },
  },
  emits: ["success"],
  setup(props, { emit }) {
    ensureAccountStyle()
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
        await props.client.sendCode(email.value.trim(), "reset_password", props.language)
      } catch (err) {
        error.value = messageOf(err)
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
        error.value = messageOf(err)
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
          field("邮箱", h("input", { type: "email", value: email.value, autocomplete: "email", onInput: (event: Event) => { email.value = textOf(event) } })),
          h("div", { class: "ak-row" }, [
            field("验证码", h("input", { value: code.value, maxlength: 6, inputmode: "numeric", onInput: (event: Event) => { code.value = textOf(event) } })),
            h("button", { type: "button", disabled: sending.value, onClick: () => void sendCode() }, sending.value ? "发送中…" : "发送验证码"),
          ]),
          field("新密码", h("input", { type: "password", value: password.value, autocomplete: "new-password", onInput: (event: Event) => { password.value = textOf(event) } })),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? "提交中…" : "重置密码"),
        ],
      )
  },
})
