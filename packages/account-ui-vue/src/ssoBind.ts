import { computed, defineComponent, getCurrentInstance, h, onBeforeUnmount, onMounted, ref, watch, type PropType } from "vue"
import { BindExistingAccountForm } from "./bindExisting"
import {
  ensureAccountStyle,
  type AccountClient,
  type AccountUser,
  type SsoBindingStatus,
  type SsoIdentity,
  type TokenPair,
} from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import {
  resolveApprovalLabels,
  resolveFormLabels,
  resolveSsoLabels,
  type ApprovalLabels,
  type FormLabels,
  type SsoLabels,
} from "./labels"
import { formatError, interpolate, textOf, type DeepPartial } from "./utils"

export const ApprovalStatusBadge = defineComponent({
  name: "ApprovalStatusBadge",
  props: {
    status: { type: String as PropType<string | null>, default: "approved" },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<ApprovalLabels>>, default: null },
    className: { type: String, default: "" },
  },
  setup(props) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveApprovalLabels(locale.value, props.labels, messages))
    return () => {
      const key = String(props.status || "approved").trim().toLowerCase()
      const text = key === "pending" ? L.value.pending : key === "rejected" ? L.value.rejected : L.value.approved
      const tone = key === "pending" ? "ak-approval-pending" : key === "rejected" ? "ak-approval-rejected" : "ak-approval-approved"
      return h("span", { class: ["ak-badge", tone, props.className].filter(Boolean).join(" ") }, text)
    }
  },
})

export const SsoBindPanel = defineComponent({
  name: "SsoBindPanel",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    bindTicket: { type: String, required: true },
    expiresIn: { type: Number, default: 600 },
    identity: { type: Object as PropType<SsoIdentity | null>, default: null },
    allowCreate: { type: Boolean, default: true },
    matchedUsername: { type: String, default: "" },
    deviceName: { type: String, default: "" },
    force: { type: Boolean, default: false },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<SsoLabels>>, default: null },
    formLabels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    className: { type: String, default: "" },
  },
  emits: ["success", "pending", "expired", "conflict"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveSsoLabels(locale.value, props.labels, messages))
    const F = computed(() => resolveFormLabels(locale.value, props.formLabels, messages))
    const tab = ref<"bind" | "create">("bind")
    const left = ref(Math.max(0, Number(props.expiresIn) || 0))
    const expired = ref(left.value <= 0)
    const error = ref("")
    const busy = ref(false)
    let tickTimer: ReturnType<typeof setInterval> | null = null

    function stopTick() {
      if (tickTimer) clearInterval(tickTimer)
      tickTimer = null
    }

    function startTick() {
      stopTick()
      if (expired.value) return
      tickTimer = setInterval(() => {
        left.value = Math.max(0, left.value - 1)
        if (left.value <= 0) {
          stopTick()
          expired.value = true
        }
      }, 1000)
    }

    watch(
      () => [props.expiresIn, props.bindTicket] as const,
      () => {
        left.value = Math.max(0, Number(props.expiresIn) || 0)
        expired.value = left.value <= 0
        startTick()
      },
    )

    onMounted(() => {
      startTick()
    })
    onBeforeUnmount(() => {
      stopTick()
    })

    async function createAccount() {
      if (busy.value || expired.value || !props.bindTicket) return
      busy.value = true
      error.value = ""
      try {
        const body = await props.client.ssoCreateAccount({
          bindTicket: props.bindTicket,
          force: props.force,
          deviceName: props.deviceName,
        })
        if (body && typeof body === "object" && "status" in body && (body as { status?: string }).status === "pending") {
          emit("pending", (body as { user: AccountUser }).user)
          return
        }
        const tokens = body as TokenPair
        if (tokens?.access_token) emit("success", tokens.access_token, { tokens })
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L.value
      const forms = F.value
      const email = props.identity?.email || ""
      const name = props.identity?.name || ""
      const children: ReturnType<typeof h>[] = [
        h("h3", labels.bindTitle),
        h("p", { class: "ak-hint" }, labels.bindHint),
        h(
          "p",
          { class: "ak-muted" },
          `${labels.identityLabel}${name ? ` · ${labels.identityName}: ${name}` : ""}${email ? ` · ${labels.identityEmail}: ${email}` : ""}`,
        ),
      ]
      if (expired.value) {
        children.push(h("p", { class: "ak-error" }, labels.ticketExpired))
        children.push(
          h("button", { type: "button", class: "ak-btn", onClick: () => emit("expired") }, labels.backToLogin),
        )
      } else {
        children.push(h("p", { class: "ak-muted" }, interpolate(labels.ticketExpiresIn, { s: String(left.value) })))
        children.push(
          h("div", { class: "ak-tabs" }, [
            h(
              "button",
              {
                type: "button",
                class: tab.value === "bind" ? "ak-tab ak-tab-active" : "ak-tab",
                onClick: () => {
                  tab.value = "bind"
                },
              },
              labels.bindExisting,
            ),
            props.allowCreate
              ? h(
                  "button",
                  {
                    type: "button",
                    class: tab.value === "create" ? "ak-tab ak-tab-active" : "ak-tab",
                    onClick: () => {
                      tab.value = "create"
                    },
                  },
                  labels.createAccount,
                )
              : null,
          ]),
        )
        if (tab.value === "bind") {
          children.push(
            h(BindExistingAccountForm, {
              client: props.client,
              bindTicket: props.bindTicket,
              bindExisting: (payload: Parameters<AccountClient["ssoBindExisting"]>[0]) => props.client.ssoBindExisting(payload),
              deviceName: props.deviceName,
              force: props.force,
              language: locale.value,
              labels: props.formLabels,
              ssoLabels: props.labels,
              defaultUsername: props.matchedUsername || props.identity?.matched_username || "",
              usernameLabel: labels.usernameOrEmail,
              submitLabel: labels.bindExisting,
              allowReclaim: true,
              completeMfaViaLogin2fa: false,
              onSuccess: (token: string, extra?: { tokens?: TokenPair; username?: string }) => {
                emit("success", token, extra)
              },
              onConflict: (err: unknown) => emit("conflict", err),
            }),
          )
        } else if (props.allowCreate) {
          children.push(
            h("div", { class: "ak-form" }, [
              h("p", { class: "ak-hint" }, interpolate(labels.createConfirm, { email: email || "—" })),
              error.value ? h("p", { class: "ak-error" }, error.value) : null,
              h(
                "button",
                { type: "button", class: "ak-btn", disabled: busy.value, onClick: () => void createAccount() },
                busy.value ? forms.submitting : labels.createAccount,
              ),
            ]),
          )
        } else {
          children.push(h("p", { class: "ak-hint" }, labels.createDisabled))
        }
      }
      return h("div", { class: ["ak-wechat", props.className].filter(Boolean).join(" ") }, children)
    }
  },
})

export const SsoBindSettings = defineComponent({
  name: "SsoBindSettings",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    passwordSet: { type: Boolean, default: true },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<SsoLabels>>, default: null },
    formLabels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    className: { type: String, default: "" },
  },
  emits: ["updated", "bindStart", "needPassword"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = computed(() => resolveSsoLabels(locale.value, props.labels, messages))
    const F = computed(() => resolveFormLabels(locale.value, props.formLabels, messages))
    const loading = ref(true)
    const status = ref<SsoBindingStatus | null>(null)
    const error = ref("")
    const info = ref("")
    const password = ref("")
    const code = ref("")
    const busy = ref(false)

    async function load() {
      loading.value = true
      error.value = ""
      try {
        const next = await props.client.ssoBinding(props.token)
        status.value = next
        emit("updated", next)
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        loading.value = false
      }
    }

    watch(
      () => props.token,
      () => {
        void load()
      },
    )
    onMounted(() => {
      void load()
    })

    async function startBind() {
      error.value = ""
      info.value = ""
      busy.value = true
      try {
        const data = await props.client.ssoBindStart(props.token)
        const url = data?.url
        if (!url) throw new Error(L.value.error)
        emit("bindStart", url)
        const listeners = getCurrentInstance()?.vnode.props as { onBindStart?: unknown } | null
        if (!listeners?.onBindStart && typeof window !== "undefined") window.location.assign(url)
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    async function unbind() {
      if (busy.value) return
      if (props.passwordSet === false) {
        emit("needPassword")
        error.value = L.value.unbindNeedPassword
        return
      }
      busy.value = true
      error.value = ""
      try {
        const next = await props.client.ssoUnbind(props.token, { password: password.value, code: code.value })
        password.value = ""
        code.value = ""
        info.value = L.value.unboundOk
        status.value = next
        emit("updated", next)
      } catch (err) {
        error.value = formatError(err, F.value, locale.value)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L.value
      const forms = F.value
      const bound = !!status.value?.bound
      const canUnbind = props.passwordSet !== false
      const children: ReturnType<typeof h>[] = [
        h("div", { class: "ak-tf-head" }, [
          h("h2", labels.section),
          h("span", { class: bound ? "ak-badge ak-badge-on" : "ak-badge ak-badge-off" }, bound ? labels.bound : labels.unbound),
        ]),
      ]
      if (loading.value) children.push(h("p", { class: "ak-muted" }, labels.loading))
      if (info.value) children.push(h("p", { class: "ak-success" }, info.value))
      if (error.value) children.push(h("p", { class: "ak-error" }, error.value))
      if (bound) {
        children.push(h("p", { class: "ak-hint" }, `${labels.emailMasked}: ${status.value?.email_masked || ""}`))
        children.push(h("p", { class: canUnbind ? "ak-hint" : "ak-warn" }, canUnbind ? labels.unbindHint : labels.unbindNeedPassword))
        children.push(
          h("form", { class: "ak-form", onSubmit: (event: Event) => { event.preventDefault(); void unbind() } }, [
            h("label", { class: "ak-field" }, [
              labels.currentPassword,
              h("input", {
                type: "password",
                value: password.value,
                disabled: !canUnbind,
                onInput: (event: Event) => {
                  password.value = textOf(event)
                },
              }),
            ]),
            h("label", { class: "ak-field" }, [
              forms.code,
              h("input", {
                value: code.value,
                disabled: !canUnbind,
                onInput: (event: Event) => {
                  code.value = textOf(event)
                },
              }),
            ]),
            h("button", { type: "submit", class: "ak-btn ak-btn-danger", disabled: busy.value || !canUnbind }, labels.unbindConfirm),
          ]),
        )
      } else {
        children.push(
          h("button", { type: "button", class: "ak-btn", disabled: busy.value, onClick: () => void startBind() }, labels.bind),
        )
      }
      return h("div", { class: ["ak-tf ak-wechat", props.className].filter(Boolean).join(" ") }, children)
    }
  },
})
