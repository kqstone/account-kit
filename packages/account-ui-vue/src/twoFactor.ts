import { defineComponent, h, onBeforeUnmount, onMounted, ref, type PropType } from "vue"
import { ensureAccountStyle, type AccountClient, type LoginSecondFactorResult, type TrustedDevice, type TwoFactorStatus } from "./client"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveTwoFactorLabels, type TwoFactorLabels } from "./labels"
import {
  canSubmitFactor,
  errorCodeOf,
  FACTOR_EMAIL,
  FACTOR_RECOVERY,
  FACTOR_TOTP,
  formatSecret,
  normalizeChallenge,
  normalizeTotpInput,
  recoveryCodesText,
  secondFactorFields,
  twoFactorErrorMessage,
  type MfaChallenge,
  type SecondFactor,
} from "./mfa"
import { renderQrDataUrl, type RenderQr } from "./qr"
import { clearTrustedDeviceTokensForUser, saveTrustedDeviceToken } from "./trustedDevice"
import { formatDateTime, interpolate, textOf, type DeepPartial } from "./utils"

function btn(kind: "primary" | "outline" | "danger" | "link", label: string, opts: { disabled?: boolean; onClick?: () => void; submit?: boolean; extraClass?: string }) {
  const cls =
    kind === "link"
      ? `ak-link${opts.extraClass ? ` ${opts.extraClass}` : ""}`
      : `ak-btn${kind === "outline" ? " ak-btn-outline" : kind === "danger" ? " ak-btn-danger" : ""}${opts.extraClass ? ` ${opts.extraClass}` : ""}`
  return h("button", { type: opts.submit ? "submit" : "button", class: cls, disabled: opts.disabled, onClick: opts.onClick }, label)
}

function field(label: string, input: ReturnType<typeof h>) {
  return h("label", { class: "ak-field" }, [label, input])
}

export const TwoFactorSettings = defineComponent({
  name: "TwoFactorSettings",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    username: { type: String, default: "" },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<TwoFactorLabels>>, default: null },
    renderQr: { type: Function as PropType<RenderQr>, default: undefined },
    className: { type: String, default: "" },
    storageKey: { type: String, default: undefined },
    brand: { type: String, default: "account-kit" },
  },
  emits: ["enabled", "disabled", "updated"],
  setup(props, { emit, slots, attrs }) {
    ensureAccountStyle()
    const loading = ref(true)
    const loadError = ref("")
    const status = ref<TwoFactorStatus | null>(null)
    const devices = ref<TrustedDevice[]>([])
    const mode = ref<"overview" | "setup-password" | "setup-scan" | "recovery" | "disable" | "regenerate">("overview")
    const busy = ref(false)
    const error = ref("")
    const info = ref("")
    const password = ref("")
    const code = ref("")
    const recoveryCode = ref("")
    const emailCode = ref("")
    const factor = ref<SecondFactor>(FACTOR_TOTP)
    const setupSecret = ref("")
    const qrDataUrl = ref("")
    const recoveryCodes = ref<string[]>([])
    const savedAck = ref(false)
    const emailMasked = ref("")
    const cooldown = ref(0)
    let cooldownTimer: ReturnType<typeof setInterval> | null = null

    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveTwoFactorLabels(locale.value, props.labels, messages)
    const errText = (e: unknown) => twoFactorErrorMessage(e, L())
    const inputs = () => ({ code: code.value, recoveryCode: recoveryCode.value, emailCode: emailCode.value })

    async function load() {
      loading.value = true
      loadError.value = ""
      try {
        status.value = await props.client.twoFactorStatus(props.token)
        devices.value = status.value.enabled ? await props.client.listTrustedDevices(props.token) : []
        emit("updated", status.value)
      } catch (e) {
        loadError.value = errText(e)
      } finally {
        loading.value = false
      }
    }

    function reset() {
      mode.value = "overview"
      error.value = ""
      password.value = ""
      code.value = ""
      recoveryCode.value = ""
      factor.value = FACTOR_TOTP
      setupSecret.value = ""
      qrDataUrl.value = ""
      emailCode.value = ""
      emailMasked.value = ""
      savedAck.value = false
    }

    function begin(next: typeof mode.value) {
      reset()
      info.value = ""
      mode.value = next
    }

    async function run(fn: () => Promise<void>) {
      busy.value = true
      error.value = ""
      try {
        await fn()
      } catch (e) {
        error.value = errText(e)
      } finally {
        busy.value = false
      }
    }

    function startCooldown(sec = 60) {
      cooldown.value = sec
      if (cooldownTimer) clearInterval(cooldownTimer)
      cooldownTimer = setInterval(() => {
        cooldown.value -= 1
        if (cooldown.value <= 0 && cooldownTimer) clearInterval(cooldownTimer)
      }, 1000)
    }

    onMounted(() => void load())
    onBeforeUnmount(() => {
      if (cooldownTimer) clearInterval(cooldownTimer)
    })

    return () => {
      const labels = L()
      const rootClass = ["ak-tf", props.className, typeof attrs.class === "string" ? attrs.class : ""].filter(Boolean).join(" ")
      const codeReady = canSubmitFactor(factor.value, inputs())
      const factorLabel =
        factor.value === FACTOR_RECOVERY ? labels.recoveryCode : factor.value === FACTOR_EMAIL ? labels.emailCode : labels.enterCode

      const totpInput = (value: string, onSet: (v: string) => void, extraClass = "ak-input ak-code") =>
        h("input", {
          value,
          class: extraClass,
          inputmode: "numeric",
          autocomplete: "one-time-code",
          maxlength: 7,
          placeholder: extraClass.includes("email") ? labels.emailCodePlaceholder : "000000",
          onInput: (event: Event) => {
            const next = normalizeTotpInput(textOf(event))
            onSet(next)
            ;(event.target as HTMLInputElement).value = next
          },
        })

      const factorLinks = (allowEmail: boolean) =>
        h("div", { class: "ak-links", style: "flex-direction:row;flex-wrap:wrap;gap:6px 16px;margin-top:4px" }, [
          factor.value !== FACTOR_TOTP ? btn("link", labels.login.useApp, { onClick: () => { factor.value = FACTOR_TOTP; error.value = "" } }) : null,
          factor.value !== FACTOR_RECOVERY
            ? btn("link", labels.login.useRecovery, { onClick: () => { factor.value = FACTOR_RECOVERY; error.value = "" } })
            : null,
          allowEmail && factor.value !== FACTOR_EMAIL
            ? btn("link", labels.skipDisable, {
                onClick: () => {
                  factor.value = FACTOR_EMAIL
                  error.value = ""
                  if (cooldown.value <= 0) void sendEmail()
                },
              })
            : null,
        ])

      async function sendEmail() {
        await run(async () => {
          try {
            const res = await props.client.sendDisableEmailCode(props.token, locale.value)
            emailMasked.value = res.email || ""
            startCooldown(Number(res.cooldown) || 60)
          } catch (e) {
            if (errorCodeOf(e) === "EMAIL_CODE_TOO_FREQUENT") startCooldown()
            throw e
          }
        })
      }

      const recoveryView = () =>
        h("div", { class: "ak-section" }, [
          h("h3", labels.recoveryTitle),
          h("p", { class: "ak-hint" }, labels.recoveryHint),
          slots.recovery?.({ codes: recoveryCodes.value }) ||
            h(
              "ul",
              { class: "ak-codes" },
              recoveryCodes.value.map((item) => h("li", { key: item }, item)),
            ),
          h("div", { class: "ak-actions" }, [
            btn("outline", labels.copy, {
              onClick: () => {
                void navigator.clipboard?.writeText(recoveryCodes.value.join("\n")).then(() => {
                  info.value = labels.copied
                })
              },
            }),
            btn("outline", labels.download, {
              onClick: () => {
                const text = recoveryCodesText(recoveryCodes.value, { username: props.username, brand: props.brand, labels })
                const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }))
                const a = document.createElement("a")
                a.href = url
                a.download = `recovery-codes-${props.username || "account"}.txt`
                document.body.appendChild(a)
                a.click()
                a.remove()
                setTimeout(() => URL.revokeObjectURL(url), 1000)
              },
            }),
          ]),
          info.value ? h("p", { class: "ak-success" }, info.value) : null,
          h("label", { class: "ak-check" }, [
            h("input", { type: "checkbox", checked: savedAck.value, onChange: (event: Event) => { savedAck.value = (event.target as HTMLInputElement).checked } }),
            h("span", labels.recoverySavedAck),
          ]),
          h("div", { class: "ak-actions" }, [
            btn("primary", labels.done, {
              disabled: !savedAck.value,
              onClick: () => {
                recoveryCodes.value = []
                reset()
                info.value = labels.enabledOk
                void load()
              },
            }),
          ]),
        ])

      const passwordForm = () =>
        h(
          "form",
          {
            class: "ak-section",
            onSubmit: (event: Event) => {
              event.preventDefault()
              void run(async () => {
                const res = await props.client.twoFactorSetup(props.token, password.value)
                password.value = ""
                setupSecret.value = res.secret
                qrDataUrl.value = await renderQrDataUrl(res.otpauth_uri, props.renderQr)
                mode.value = "setup-scan"
              })
            },
          },
          [
            field(labels.currentPassword, h("input", { class: "ak-input", type: "password", value: password.value, autocomplete: "current-password", onInput: (event: Event) => { password.value = textOf(event) } })),
            error.value ? h("p", { class: "ak-error" }, error.value) : null,
            h("div", { class: "ak-actions" }, [
              btn("outline", labels.cancel, { disabled: busy.value, onClick: reset }),
              btn("primary", labels.next, { disabled: busy.value || !password.value, submit: true }),
            ]),
          ],
        )

      const scanForm = () =>
        h(
          "form",
          {
            class: "ak-section",
            onSubmit: (event: Event) => {
              event.preventDefault()
              void run(async () => {
                const res = await props.client.twoFactorEnable(props.token, code.value)
                recoveryCodes.value = res.recovery_codes || []
                setupSecret.value = ""
                qrDataUrl.value = ""
                code.value = ""
                savedAck.value = false
                mode.value = "recovery"
                emit("enabled", res)
              })
            },
          },
          [
            h("ol", { class: "ak-steps" }, [h("li", labels.scanStep1), h("li", labels.scanStep2)]),
            slots.qr?.({ dataUrl: qrDataUrl.value, secret: setupSecret.value }) ||
              h("div", { class: "ak-qr-wrap" }, [
                qrDataUrl.value ? h("img", { src: qrDataUrl.value, class: "ak-qr", alt: "QR" }) : h("p", { class: "ak-muted" }, labels.qrUnavailable),
                h("div", { class: "ak-secret" }, [
                  h("span", { class: "ak-muted" }, labels.manualEntry),
                  h("code", formatSecret(setupSecret.value)),
                  btn("link", labels.copy, {
                    onClick: () => {
                      void navigator.clipboard?.writeText(setupSecret.value).then(() => {
                        info.value = labels.copied
                      })
                    },
                  }),
                ]),
              ]),
            field(labels.enterCode, totpInput(code.value, (v) => { code.value = v })),
            error.value ? h("p", { class: "ak-error" }, error.value) : null,
            h("div", { class: "ak-actions" }, [
              btn("outline", labels.cancel, { disabled: busy.value, onClick: reset }),
              btn("primary", labels.enable, { disabled: busy.value || code.value.length !== 6, submit: true }),
            ]),
          ],
        )

      const passwordCodeForm = () =>
        h(
          "form",
          {
            class: "ak-section",
            onSubmit: (event: Event) => {
              event.preventDefault()
              void run(async () => {
                const payload = { password: password.value, ...secondFactorFields(factor.value, inputs()) }
                if (mode.value === "disable") {
                  await props.client.twoFactorDisable(props.token, payload)
                  if (props.username) clearTrustedDeviceTokensForUser(props.username, props.storageKey)
                  reset()
                  info.value = labels.disabledOk
                  emit("disabled")
                  await load()
                } else {
                  const res = await props.client.regenerateRecoveryCodes(props.token, payload)
                  reset()
                  recoveryCodes.value = res.recovery_codes || []
                  mode.value = "recovery"
                }
              })
            },
          },
          [
            h("h3", mode.value === "disable" ? labels.disableTitle : labels.regenerateTitle),
            mode.value === "disable" ? h("p", { class: "ak-hint" }, labels.disableHint) : null,
            field(labels.currentPassword, h("input", { class: "ak-input", type: "password", value: password.value, autocomplete: "current-password", onInput: (event: Event) => { password.value = textOf(event) } })),
            field(
              factorLabel,
              factor.value === FACTOR_TOTP
                ? totpInput(code.value, (v) => { code.value = v })
                : factor.value === FACTOR_RECOVERY
                  ? h("input", { class: "ak-input", value: recoveryCode.value, autocomplete: "off", placeholder: "xxxx-xxxx", onInput: (event: Event) => { recoveryCode.value = textOf(event) } })
                  : h("span", { class: "ak-row" }, [
                      totpInput(emailCode.value, (v) => { emailCode.value = v }, "ak-input ak-code"),
                      btn("outline", cooldown.value > 0 ? interpolate(labels.resendIn, { s: cooldown.value }) : labels.sendEmailCode, {
                        disabled: busy.value || cooldown.value > 0,
                        onClick: () => void sendEmail(),
                      }),
                    ]),
            ),
            factor.value === FACTOR_EMAIL && emailMasked.value ? h("p", { class: "ak-muted" }, interpolate(labels.emailSentTo, { email: emailMasked.value })) : null,
            factorLinks(mode.value === "disable" && !!status.value?.email_available),
            error.value ? h("p", { class: "ak-error" }, error.value) : null,
            h("div", { class: "ak-actions" }, [
              btn("outline", labels.cancel, { disabled: busy.value, onClick: reset }),
              btn(mode.value === "disable" ? "danger" : "primary", mode.value === "disable" ? labels.disable : labels.regenerate, {
                disabled: busy.value || !password.value || !codeReady,
                submit: true,
              }),
            ]),
          ],
        )

      const overview = () =>
        h("div", { class: "ak-section" }, [
          info.value ? h("p", { class: "ak-success" }, info.value) : null,
          !status.value?.enabled
            ? h("div", { class: "ak-actions" }, [btn("primary", labels.enable, { onClick: () => begin("setup-password") })])
            : [
                h("p", { class: "ak-muted" }, interpolate(labels.recoveryRemaining, { n: status.value.recovery_codes_remaining })),
                h("div", { class: "ak-actions" }, [
                  btn("outline", labels.regenerate, { onClick: () => begin("regenerate") }),
                  btn("danger", labels.disable, { onClick: () => begin("disable") }),
                ]),
                h("div", { class: "ak-devices" }, [
                  h("div", { class: "ak-tf-head" }, [
                    h("h3", labels.trustedDevices),
                    devices.value.length
                      ? btn("link", labels.revokeAll, {
                          extraClass: "ak-danger",
                          disabled: busy.value,
                          onClick: () =>
                            void run(async () => {
                              await props.client.revokeAllTrustedDevices(props.token)
                              devices.value = []
                              if (props.username) clearTrustedDeviceTokensForUser(props.username, props.storageKey)
                            }),
                        })
                      : null,
                  ]),
                  h("p", { class: "ak-muted" }, interpolate(labels.trustedDevicesHint, { days: status.value.trusted_device_days })),
                  !devices.value.length
                    ? h("p", { class: "ak-muted" }, labels.noTrustedDevices)
                    : h(
                        "ul",
                        { class: "ak-device-list" },
                        devices.value.map((device) =>
                          h("li", { key: device.id }, [
                            h("div", [
                              h("div", { class: "ak-device-name" }, device.device_name),
                              h("div", { class: "ak-muted" }, `${labels.lastUsed} ${formatDateTime(device.last_used_at, locale.value)} · ${labels.expires} ${formatDateTime(device.expires_at, locale.value)}`),
                            ]),
                            btn("outline", labels.revoke, {
                              extraClass: "ak-btn-small",
                              disabled: busy.value,
                              onClick: () =>
                                void run(async () => {
                                  await props.client.revokeTrustedDevice(props.token, device.id)
                                  devices.value = devices.value.filter((item) => item.id !== device.id)
                                }),
                            }),
                          ]),
                        ),
                      ),
                ]),
              ],
        ])

      let body: ReturnType<typeof h> | string | null = null
      if (loading.value) body = h("div", { class: "ak-muted" }, labels.loading)
      else if (loadError.value) body = h("div", { class: "ak-error" }, loadError.value)
      else if (mode.value === "recovery") body = recoveryView()
      else if (mode.value === "setup-password") body = passwordForm()
      else if (mode.value === "setup-scan") body = scanForm()
      else if (mode.value === "disable" || mode.value === "regenerate") body = passwordCodeForm()
      else if (status.value) body = overview()

      return h("div", { class: rootClass }, [
        h("div", { class: "ak-tf-head" }, [
          h("h2", labels.title),
          status.value
            ? h("span", { class: ["ak-badge", status.value.enabled ? "ak-badge-on" : "ak-badge-off"] }, status.value.enabled ? labels.statusOn : labels.statusOff)
            : null,
        ]),
        h("p", { class: "ak-hint" }, labels.description),
        slots.header?.({ status: status.value }),
        body,
        slots.footer?.({ status: status.value }),
      ])
    }
  },
})

export const TwoFactorLoginDialog = defineComponent({
  name: "TwoFactorLoginDialog",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    challenge: { type: Object as PropType<MfaChallenge | Record<string, unknown>>, required: true },
    deviceName: { type: String, default: "" },
    force: { type: Boolean, default: false },
    trustedDays: { type: Number, default: 0 },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<TwoFactorLabels>>, default: null },
    className: { type: String, default: "" },
    scope: { type: String, default: "" },
    storageKey: { type: String, default: undefined },
  },
  emits: ["success", "expired", "cancel"],
  setup(props, { emit, attrs }) {
    ensureAccountStyle()
    const mode = ref<"code" | "conflict">("code")
    const factor = ref<SecondFactor>(FACTOR_TOTP)
    const code = ref("")
    const recoveryCode = ref("")
    const emailCode = ref("")
    const trustDevice = ref(false)
    const busy = ref(false)
    const error = ref("")
    const conflictDevice = ref("")
    const emailMasked = ref("")
    const cooldown = ref(0)
    let cooldownTimer: ReturnType<typeof setInterval> | null = null

    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const L = () => resolveTwoFactorLabels(locale.value, props.labels, messages)
    const challengeInfo = () => normalizeChallenge(props.challenge)
    const inputs = () => ({ code: code.value, recoveryCode: recoveryCode.value, emailCode: emailCode.value })

    function startCooldown(sec = 60) {
      cooldown.value = sec
      if (cooldownTimer) clearInterval(cooldownTimer)
      cooldownTimer = setInterval(() => {
        cooldown.value -= 1
        if (cooldown.value <= 0 && cooldownTimer) clearInterval(cooldownTimer)
      }, 1000)
    }

    onBeforeUnmount(() => {
      if (cooldownTimer) clearInterval(cooldownTimer)
    })

    async function submit(force: boolean) {
      if (busy.value) return
      const labels = L()
      const info = challengeInfo()
      if (!info) return
      busy.value = true
      error.value = ""
      try {
        const fields = mode.value === "conflict" ? { code: "", recoveryCode: "", emailCode: "" } : secondFactorFields(factor.value, inputs())
        const data = await props.client.loginSecondFactor({
          challengeToken: info.challengeToken,
          ...fields,
          trustDevice: trustDevice.value,
          force,
          deviceName: props.deviceName,
        })
        if (data.trusted_device_token && props.scope) {
          saveTrustedDeviceToken(props.scope, data.trusted_device_token, data.trusted_device_expires_at, props.storageKey)
        }
        emit("success", data as LoginSecondFactorResult)
      } catch (e) {
        const status = e && typeof e === "object" && "status" in e ? Number((e as { status: number }).status) : 0
        const errCode = errorCodeOf(e)
        if (status === 409 && errCode === "ALREADY_LOGGED_IN") {
          const detail = e && typeof e === "object" && "body" in e ? (e as { body?: { detail?: { device_name?: string } } }).body?.detail : null
          conflictDevice.value = detail?.device_name || ""
          mode.value = "conflict"
        } else if (errCode === "MFA_CHALLENGE_INVALID" || errCode === "MFA_TOO_MANY_ATTEMPTS") {
          emit("expired", twoFactorErrorMessage(e, labels))
        } else {
          error.value = twoFactorErrorMessage(e, labels)
          if (factor.value === FACTOR_EMAIL) emailCode.value = ""
          else code.value = ""
        }
      } finally {
        busy.value = false
      }
    }

    async function sendEmail() {
      if (busy.value) return
      const labels = L()
      const info = challengeInfo()
      if (!info) return
      busy.value = true
      error.value = ""
      try {
        const res = await props.client.sendLoginEmailCode(info.challengeToken, locale.value)
        emailMasked.value = res.email || ""
        startCooldown(Number(res.cooldown) || 60)
      } catch (e) {
        const errCode = errorCodeOf(e)
        if (errCode === "MFA_CHALLENGE_INVALID") emit("expired", twoFactorErrorMessage(e, labels))
        else error.value = twoFactorErrorMessage(e, labels)
        if (errCode === "EMAIL_CODE_TOO_FREQUENT") startCooldown()
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L()
      const info = challengeInfo()
      const days = props.trustedDays || info?.trustedDays || 30
      const emailAvailable = !!(info?.emailAvailable)
      const canSubmit = canSubmitFactor(factor.value, inputs())
      const hint =
        factor.value === FACTOR_RECOVERY ? labels.login.recoveryHint : factor.value === FACTOR_EMAIL ? labels.login.emailHint : labels.login.hint
      const rootClass = ["ak-overlay", props.className, typeof attrs.class === "string" ? attrs.class : ""].filter(Boolean).join(" ")

      const totpInput = (value: string, onSet: (v: string) => void, autoSubmit = false) =>
        h("input", {
          value,
          class: "ak-input ak-code",
          inputmode: "numeric",
          autocomplete: "one-time-code",
          maxlength: 7,
          placeholder: factor.value === FACTOR_EMAIL ? labels.emailCodePlaceholder : "000000",
          onInput: (event: Event) => {
            const next = normalizeTotpInput(textOf(event))
            onSet(next)
            ;(event.target as HTMLInputElement).value = next
            if (autoSubmit && next.length === 6 && !busy.value) void submit(props.force)
          },
        })

      const conflict = () =>
        h("div", { class: "ak-dialog", role: "dialog", "aria-modal": "true" }, [
          h("h3", labels.login.alreadyLoggedInTitle),
          h("p", { class: "ak-hint" }, interpolate(labels.login.alreadyLoggedInBody, { device: conflictDevice.value || labels.login.unknownDevice })),
          h("p", { class: "ak-warn" }, labels.login.unsavedDataWarning),
          error.value ? h("div", { class: "ak-error" }, error.value) : null,
          h("div", { class: "ak-actions", style: "justify-content:flex-end" }, [
            btn("outline", labels.login.forceLoginCancel, { disabled: busy.value, onClick: () => { if (!busy.value) emit("cancel") } }),
            btn("primary", labels.login.forceLoginConfirm, { disabled: busy.value, onClick: () => void submit(true) }),
          ]),
        ])

      const codeView = () =>
        h("div", { class: "ak-dialog", role: "dialog", "aria-modal": "true" }, [
          h("h3", factor.value === FACTOR_EMAIL ? labels.login.emailTitle : labels.login.title),
          h("p", { class: "ak-hint" }, hint),
          h(
            "form",
            {
              onSubmit: (event: Event) => {
                event.preventDefault()
                void submit(props.force)
              },
            },
            [
              factor.value === FACTOR_TOTP
                ? totpInput(code.value, (v) => { code.value = v }, true)
                : factor.value === FACTOR_RECOVERY
                  ? h("input", {
                      class: "ak-input",
                      value: recoveryCode.value,
                      autocomplete: "off",
                      autocapitalize: "none",
                      spellcheck: false,
                      placeholder: "xxxx-xxxx",
                      onInput: (event: Event) => { recoveryCode.value = textOf(event) },
                    })
                  : [
                      h("span", { class: "ak-row" }, [
                        totpInput(emailCode.value, (v) => { emailCode.value = v }),
                        btn("outline", cooldown.value > 0 ? interpolate(labels.resendIn, { s: cooldown.value }) : labels.sendEmailCode, {
                          disabled: busy.value || cooldown.value > 0,
                          onClick: () => void sendEmail(),
                        }),
                      ]),
                      emailMasked.value ? h("p", { class: "ak-muted" }, interpolate(labels.emailSentTo, { email: emailMasked.value })) : null,
                    ],
              h("label", { class: "ak-check" }, [
                h("input", { type: "checkbox", checked: trustDevice.value, onChange: (event: Event) => { trustDevice.value = (event.target as HTMLInputElement).checked } }),
                h("span", interpolate(labels.login.trustDevice, { days })),
              ]),
              error.value ? h("div", { class: "ak-error" }, error.value) : null,
              h("div", { class: "ak-actions", style: "justify-content:flex-end" }, [
                btn("outline", labels.cancel, { disabled: busy.value, onClick: () => { if (!busy.value) emit("cancel") } }),
                btn("primary", busy.value ? labels.verifying : labels.verify, { disabled: busy.value || !canSubmit, submit: true }),
              ]),
            ],
          ),
          h("div", { class: "ak-links" }, [
            factor.value !== FACTOR_TOTP ? btn("link", labels.login.useApp, { onClick: () => { factor.value = FACTOR_TOTP; error.value = "" } }) : null,
            factor.value !== FACTOR_RECOVERY ? btn("link", labels.login.useRecovery, { onClick: () => { factor.value = FACTOR_RECOVERY; error.value = "" } }) : null,
            emailAvailable && factor.value !== FACTOR_EMAIL
              ? btn("link", labels.login.skip, {
                  onClick: () => {
                    factor.value = FACTOR_EMAIL
                    error.value = ""
                    if (cooldown.value <= 0) void sendEmail()
                  },
                })
              : null,
          ]),
        ])

      return h(
        "div",
        {
          class: rootClass,
          onClick: (event: Event) => {
            if (event.target === event.currentTarget && !busy.value) emit("cancel")
          },
        },
        [mode.value === "conflict" ? conflict() : codeView()],
      )
    }
  },
})
