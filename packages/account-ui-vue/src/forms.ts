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
  },
  emits: ["success"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const username = ref("")
    const password = ref("")
    const error = ref("")
    const busy = ref(false)
    const force = ref(false)

    async function submit() {
      error.value = ""
      busy.value = true
      try {
        const token = await props.client.login(username.value.trim(), password.value, {
          force: force.value,
          deviceName: props.deviceName || undefined,
        })
        emit("success", token.access_token)
      } catch (err) {
        const body = err instanceof AccountApiError ? err.body : null
        const detail =
          body && typeof body === "object" && "detail" in body
            ? (body as { detail?: { code?: string; device_name?: string } }).detail
            : null
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
  },
  emits: ["success"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const username = ref("")
    const email = ref("")
    const password = ref("")
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
        const user = await props.client.register({
          username: username.value.trim(),
          email: email.value.trim(),
          password: password.value,
          code: code.value.trim(),
          role: role.value || undefined,
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
