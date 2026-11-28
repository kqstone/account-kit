import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, type PropType } from "vue"
import {
  AccountApiError,
  ensureAccountStyle,
  type AccountClient,
  type TokenPair,
  type WechatBindStatus,
  type WechatStartResult,
} from "./client"
import { BindExistingAccountForm } from "./bindExisting"
import { CodeInputRow } from "./authShell"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveFormLabels, resolveWechatLabels, type FormLabels, type WechatLabels } from "./labels"
import { useSendCode } from "./sendCode"
import { formatError, interpolate, textOf, type DeepPartial } from "./utils"

function field(label: string, input: ReturnType<typeof h>) {
  return h("label", { class: "ak-field" }, [label, input])
}

function imageSrc(data: WechatStartResult) {
  return `data:${data.mime || "image/png"};base64,${data.image_base64}`
}

export const WechatQrLogin = defineComponent({
  name: "WechatQrLogin",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    deviceName: { type: String, default: "" },
    pollMs: { type: Number, default: 2000 },
    force: { type: Boolean, default: false },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<WechatLabels>>, default: null },
    formLabels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    className: { type: String, default: "" },
  },
  emits: ["success", "unbound", "conflict", "registered"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveWechatLabels(locale.value, props.labels, messages))
    const F = computed(() => resolveFormLabels(locale.value, props.formLabels, messages))
    const phase = ref<"loading" | "qr" | "expired" | "unbound" | "unconfigured" | "error">("loading")
    const error = ref("")
    const started = ref<WechatStartResult | null>(null)
    const expiresLeft = ref(0)
    const scannedName = ref("")
    const tab = ref<"bind" | "register">("bind")
    const username = ref("")
    const password = ref("")
    const email = ref("")
    const code = ref("")
    const send = useSendCode({ requireEmail: true })
    const busy = ref(false)
    const ticket = ref("")
    let pollTimer: ReturnType<typeof setInterval> | null = null
    let tickTimer: ReturnType<typeof setInterval> | null = null

    function stop() {
      if (pollTimer) clearInterval(pollTimer)
      if (tickTimer) clearInterval(tickTimer)
      pollTimer = null
      tickTimer = null
    }

    async function cancel() {
      if (ticket.value) {
        try {
          await props.client.cancelWechatLogin(ticket.value)
        } catch {
          /* ignore */
        }
      }
    }

    async function start() {
      stop()
      error.value = ""
      scannedName.value = ""
      phase.value = "loading"
      try {
        const data = await props.client.startWechatLogin({ deviceName: props.deviceName, force: props.force })
        started.value = data
        ticket.value = data.ticket
        expiresLeft.value = Number(data.expires_in) || 120
        phase.value = "qr"
        pollTimer = setInterval(() => void poll(), Math.max(500, props.pollMs || 2000))
        tickTimer = setInterval(() => {
          expiresLeft.value = Math.max(0, expiresLeft.value - 1)
          if (expiresLeft.value <= 0) {
            stop()
            phase.value = "expired"
          }
        }, 1000)
      } catch (err) {
        const status = err instanceof AccountApiError ? err.status : 0
        const errCode = err instanceof AccountApiError ? err.code : ""
        if (status === 503 || errCode === "WECHAT_NOT_CONFIGURED") {
          phase.value = "unconfigured"
          error.value = L.value.notConfigured
          return
        }
        phase.value = "error"
        error.value = formatError(err, F.value, locale.value)
      }
    }

    async function poll() {
      if (!ticket.value) return
      try {
        const data = await props.client.wechatLoginStatus(ticket.value)
        if (data.status === "scanned" && data.username) scannedName.value = data.username
        if (data.status === "unbound") {
          stop()
          phase.value = "unbound"
          emit("unbound", { bindTicket: data.bind_ticket || ticket.value })
          return
        }
        if (data.status === "expired" || data.status === "cancelled") {
          stop()
          phase.value = "expired"
          return
        }
        if (data.access_token) {
          stop()
          emit("success", data.access_token, { tokens: data as TokenPair })
        }
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      }
    }

    async function sendRegisterCode() {
      error.value = ""
      await send.run(() => props.client.sendCode(email.value.trim(), "register", locale.value), {
        email: email.value,
        labels: F.value,
        locale: locale.value,
        extraHints: { EMAIL_TAKEN: F.value.emailTakenHint },
      })
    }

    async function submitRegister() {
      if (busy.value || !ticket.value) return
      busy.value = true
      error.value = ""
      try {
        const body = await props.client.wechatRegister({
          bind_ticket: ticket.value,
          username: username.value.trim(),
          email: email.value.trim(),
          password: password.value,
          code: code.value.trim(),
        })
        if (body && typeof body === "object" && "access_token" in body && (body as TokenPair).access_token) {
          const tokens = body as TokenPair
          emit("success", tokens.access_token, { tokens })
        } else {
          emit("registered", body)
        }
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    onMounted(() => {
      void start()
    })
    onBeforeUnmount(() => {
      stop()
      void cancel()
    })

    return () => {
      const labels = L.value
      const forms = F.value
      const rootClass = ["ak-wechat", props.className].filter(Boolean).join(" ")
      const qr = started.value
      const children: ReturnType<typeof h>[] = [h("h3", labels.title)]
      if (phase.value === "unconfigured") {
        children.push(h("p", { class: "ak-error" }, labels.notConfigured))
      } else if (phase.value === "expired") {
        children.push(h("p", { class: "ak-hint" }, labels.expired))
        children.push(h("button", { type: "button", class: "ak-btn", onClick: () => void start() }, labels.refresh))
      } else if (phase.value === "unbound") {
        children.push(h("p", { class: "ak-hint" }, labels.unboundHint))
        children.push(
          h("div", { class: "ak-tabs" }, [
            h("button", { type: "button", class: tab.value === "bind" ? "ak-tab ak-tab-active" : "ak-tab", onClick: () => { tab.value = "bind" } }, labels.bindExisting),
            h("button", { type: "button", class: tab.value === "register" ? "ak-tab ak-tab-active" : "ak-tab", onClick: () => { tab.value = "register" } }, labels.registerTab),
          ]),
        )
        if (tab.value === "bind") {
          children.push(
            h(BindExistingAccountForm, {
              client: props.client,
              bindTicket: ticket.value,
              bindExisting: (payload: Parameters<AccountClient["wechatBindExisting"]>[0]) => props.client.wechatBindExisting(payload),
              deviceName: props.deviceName,
              force: props.force,
              language: locale.value,
              labels: props.formLabels,
              usernameLabel: forms.username,
              submitLabel: labels.bindExisting,
              completeMfaViaLogin2fa: true,
              onSuccess: (token: string, extra?: { tokens?: TokenPair; username?: string }) => {
                emit("success", token, extra)
              },
              onConflict: (err: unknown) => emit("conflict", err),
            }),
          )
        } else {
          children.push(
            h("form", { class: "ak-form", onSubmit: (event: Event) => { event.preventDefault(); void submitRegister() } }, [
              field(forms.username, h("input", { value: username.value, autocomplete: "username", onInput: (event: Event) => { username.value = textOf(event) } })),
              field(forms.email, h("input", { type: "email", value: email.value, autocomplete: "email", onInput: (event: Event) => { email.value = textOf(event) } })),
              field(forms.password, h("input", { type: "password", value: password.value, autocomplete: "new-password", onInput: (event: Event) => { password.value = textOf(event) } })),
              h(CodeInputRow, { label: forms.code, modelValue: code.value, maxlength: 6, inputmode: "numeric", autocomplete: "one-time-code", buttonText: send.buttonText(forms, forms.sendCode, email.value), buttonDisabled: send.buttonDisabled(email.value), "onUpdate:modelValue": (v: string) => { code.value = v }, onButtonClick: () => void sendRegisterCode() }),
              send.info.value ? h("p", { class: "ak-success" }, send.info.value) : null,
              error.value || send.error.value ? h("p", { class: "ak-error" }, error.value || send.error.value) : null,
              h("button", { type: "submit", disabled: busy.value }, busy.value ? forms.submitting : forms.register),
            ]),
          )
        }
      } else {
        children.push(h("p", { class: "ak-hint" }, scannedName.value ? labels.scanned : labels.hint))
        if (qr) children.push(h("img", { class: "ak-wechat-qr", src: imageSrc(qr), alt: labels.title }))
        children.push(h("p", { class: "ak-muted" }, interpolate(labels.expiresIn, { s: String(expiresLeft.value) })))
        if (phase.value === "error" && error.value) children.push(h("p", { class: "ak-error" }, error.value))
        children.push(h("button", { type: "button", class: "ak-btn ak-btn-outline", onClick: () => void start() }, labels.refresh))
      }
      return h("div", { class: rootClass }, children)
    }
  },
})

export const WechatBindSettings = defineComponent({
  name: "WechatBindSettings",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<WechatLabels>>, default: null },
    formLabels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    className: { type: String, default: "" },
    pollMs: { type: Number, default: 2000 },
  },
  emits: ["updated"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveWechatLabels(locale.value, props.labels, messages))
    const F = computed(() => resolveFormLabels(locale.value, props.formLabels, messages))
    const loading = ref(true)
    const status = ref<WechatBindStatus | null>(null)
    const error = ref("")
    const info = ref("")
    const qr = ref<WechatStartResult | null>(null)
    const expiresLeft = ref(0)
    const expired = ref(false)
    const password = ref("")
    const code = ref("")
    const busy = ref(false)
    let pollTimer: ReturnType<typeof setInterval> | null = null
    let tickTimer: ReturnType<typeof setInterval> | null = null
    let ticket = ""

    function stop() {
      if (pollTimer) clearInterval(pollTimer)
      if (tickTimer) clearInterval(tickTimer)
      pollTimer = null
      tickTimer = null
    }

    async function load() {
      loading.value = true
      error.value = ""
      try {
        status.value = await props.client.wechatBindStatus(props.token)
        emit("updated", status.value)
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        loading.value = false
      }
    }

    async function startBind() {
      stop()
      error.value = ""
      info.value = ""
      expired.value = false
      try {
        const data = await props.client.startWechatBind(props.token)
        qr.value = data
        ticket = data.ticket
        expiresLeft.value = Number(data.expires_in) || 120
        pollTimer = setInterval(() => void poll(), Math.max(500, props.pollMs || 2000))
        tickTimer = setInterval(() => {
          expiresLeft.value = Math.max(0, expiresLeft.value - 1)
          if (expiresLeft.value <= 0) {
            stop()
            expired.value = true
          }
        }, 1000)
      } catch (err) {
        const statusCode = err instanceof AccountApiError ? err.status : 0
        if (statusCode === 503) error.value = L.value.notConfigured
        else error.value = formatError(err, F.value, locale.value)
      }
    }

    async function poll() {
      if (!ticket) return
      try {
        const data = await props.client.wechatLoginStatus(ticket)
        if (data.status === "expired" || data.status === "cancelled") {
          stop()
          expired.value = true
          return
        }
        if (data.status === "confirmed" || data.status === "consumed") {
          stop()
          qr.value = null
          ticket = ""
          info.value = L.value.boundOk
          await load()
        }
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      }
    }

    async function unbind() {
      if (busy.value) return
      busy.value = true
      error.value = ""
      try {
        await props.client.unbindWechat(props.token, { password: password.value, code: code.value })
        password.value = ""
        code.value = ""
        info.value = L.value.unboundOk
        await load()
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    onMounted(() => {
      void load()
    })
    onBeforeUnmount(() => {
      stop()
    })

    return () => {
      const labels = L.value
      const forms = F.value
      const bound = !!status.value?.bound
      const children: ReturnType<typeof h>[] = [
        h("div", { class: "ak-tf-head" }, [
          h("h2", labels.title),
          h("span", { class: bound ? "ak-badge ak-badge-on" : "ak-badge ak-badge-off" }, bound ? labels.bound : labels.unbound),
        ]),
      ]
      if (loading.value) children.push(h("p", { class: "ak-muted" }, labels.loading))
      if (info.value) children.push(h("p", { class: "ak-success" }, info.value))
      if (error.value) children.push(h("p", { class: "ak-error" }, error.value))
      if (bound) {
        children.push(h("p", { class: "ak-hint" }, `${labels.openid}: ${status.value?.openid_masked || ""}`))
        children.push(h("p", { class: "ak-hint" }, labels.unbindHint))
        children.push(
          h("form", { class: "ak-form", onSubmit: (event: Event) => { event.preventDefault(); void unbind() } }, [
            field(labels.currentPassword, h("input", { type: "password", value: password.value, onInput: (event: Event) => { password.value = textOf(event) } })),
            field(forms.code, h("input", { value: code.value, onInput: (event: Event) => { code.value = textOf(event) } })),
            h("button", { type: "submit", class: "ak-btn ak-btn-danger", disabled: busy.value }, labels.unbindConfirm),
          ]),
        )
      } else {
        if (qr.value && !expired.value) {
          children.push(h("img", { class: "ak-wechat-qr", src: imageSrc(qr.value), alt: labels.bind }))
          children.push(h("p", { class: "ak-muted" }, interpolate(labels.expiresIn, { s: String(expiresLeft.value) })))
        }
        if (expired.value) children.push(h("p", { class: "ak-hint" }, labels.expired))
        children.push(h("button", { type: "button", class: "ak-btn", onClick: () => void startBind() }, qr.value ? labels.refresh : labels.bind))
      }
      return h("div", { class: ["ak-tf ak-wechat", props.className].filter(Boolean).join(" ") }, children)
    }
  },
})
