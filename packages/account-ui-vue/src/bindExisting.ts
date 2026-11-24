import { computed, defineComponent, h, ref, type PropType } from "vue"
import { AccountApiError, ensureAccountStyle, type AccountClient, type BindExistingPayload, type TokenPair } from "./client"

export type BindExistingSuccessExtra = { tokens?: TokenPair; username?: string }
import { CodeInputRow } from "./authShell"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveFormLabels, resolveSsoLabels, type FormLabels, type SsoLabels } from "./labels"
import { getMfaChallenge, type MfaChallenge } from "./mfa"
import { TwoFactorLoginDialog, type TwoFactorVerifyPayload } from "./twoFactor"
import { formatError, interpolate, textOf, type DeepPartial } from "./utils"

function field(label: string, input: ReturnType<typeof h>) {
  return h("label", { class: "ak-field" }, [label, input])
}

export const BindExistingAccountForm = defineComponent({
  name: "BindExistingAccountForm",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    bindTicket: { type: String, required: true },
    bindExisting: { type: Function as PropType<(payload: BindExistingPayload) => Promise<TokenPair>>, required: true },
    deviceName: { type: String, default: "" },
    force: { type: Boolean, default: false },
    language: { type: String, default: undefined },
    labels: { type: Object as PropType<DeepPartial<FormLabels>>, default: null },
    ssoLabels: { type: Object as PropType<DeepPartial<SsoLabels>>, default: null },
    defaultUsername: { type: String, default: "" },
    usernameLabel: { type: String, default: "" },
    submitLabel: { type: String, default: "" },
    allowReclaim: { type: Boolean, default: false },
    completeMfaViaLogin2fa: { type: Boolean, default: false },
  },
  emits: ["success", "conflict"],
  setup(props, { emit }) {
    ensureAccountStyle()
    const locale = useKitLocale(() => props.language)
    const { messages } = useAccountI18n()
    const F = computed(() => resolveFormLabels(locale.value, props.labels, messages))
    const S = computed(() => resolveSsoLabels(locale.value, props.ssoLabels, messages))
    const username = ref(props.defaultUsername || "")
    const password = ref("")
    const error = ref("")
    const busy = ref(false)
    const bindForce = ref(false)
    const captchaNeeded = ref(false)
    const captchaId = ref("")
    const captchaImage = ref("")
    const captchaCode = ref("")
    const mfa = ref<(MfaChallenge & { username?: string }) | null>(null)
    const reclaim = ref(false)
    const orphanUsername = ref("")

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
        error.value = F.value.captchaLoadFailed
      }
    }

    function payload(extra: Partial<BindExistingPayload> = {}): BindExistingPayload {
      return {
        bindTicket: props.bindTicket,
        username: username.value.trim(),
        password: password.value,
        force: bindForce.value || props.force || extra.force,
        deviceName: extra.deviceName || props.deviceName,
        captchaId: extra.captchaId,
        captchaCode: extra.captchaCode,
        code: extra.code,
        recoveryCode: extra.recoveryCode,
        emailCode: extra.emailCode,
        reclaim: reclaim.value || extra.reclaim,
      }
    }

    async function submitBind() {
      if (busy.value || !props.bindTicket) return
      error.value = ""
      const usedCaptcha = captchaNeeded.value
      if (usedCaptcha && (!captchaId.value || !captchaCode.value.trim())) {
        error.value = F.value.captchaEnter
        return
      }
      busy.value = true
      try {
        const tokens = await props.bindExisting(
          payload({
            captchaId: usedCaptcha ? captchaId.value : undefined,
            captchaCode: usedCaptcha ? captchaCode.value.trim() : undefined,
          }),
        )
        captchaNeeded.value = false
        emit("success", tokens.access_token, { tokens, username: username.value })
      } catch (err) {
        const body = err instanceof AccountApiError ? err.body : null
        const detail =
          body && typeof body === "object" && "detail" in body
            ? (body as {
                detail?: { code?: string; device_name?: string; captcha_required?: boolean; orphan_username?: string } | string
              }).detail
            : null
        const info = detail && typeof detail === "object" ? detail : null
        const status = err instanceof AccountApiError ? err.status : 0
        const code = info?.code || (err instanceof AccountApiError ? err.code : "")
        if (usedCaptcha) captchaNeeded.value = false
        if (status === 428 || code === "CAPTCHA_REQUIRED" || code === "CAPTCHA_INVALID" || info?.captcha_required) {
          captchaNeeded.value = true
          await loadCaptcha()
          error.value =
            code === "CAPTCHA_INVALID"
              ? F.value.captchaInvalid
              : status === 428 || code === "CAPTCHA_REQUIRED"
                ? F.value.captchaEnter
                : formatError(err, F.value, locale.value)
        } else if (status === 409 && code === "ALREADY_LOGGED_IN") {
          bindForce.value = true
          emit("conflict", err)
          error.value = interpolate(F.value.alreadyLoggedIn, {
            device: info?.device_name || F.value.errors.UNKNOWN_DEVICE,
          })
        } else if (props.allowReclaim && (status === 409 || status === 400) && code === "SSO_ORPHAN_PENDING") {
          reclaim.value = true
          const orphan =
            String(info?.orphan_username || "") ||
            (err instanceof AccountApiError && err.body && typeof err.body === "object"
              ? String((err.body as { params?: { orphan_username?: string } }).params?.orphan_username || "")
              : "")
          orphanUsername.value = orphan
          error.value = interpolate(S.value.reclaimHint, { username: orphan || "—" })
        } else {
          const challenge = getMfaChallenge(err)
          if (challenge) {
            mfa.value = { ...challenge, bindTicket: challenge.bindTicket || props.bindTicket, username: username.value }
            return
          }
          error.value = formatError(err, F.value, locale.value)
        }
      } finally {
        busy.value = false
      }
    }

    async function verifyMfa(fields: TwoFactorVerifyPayload) {
      return props.bindExisting(
        payload({
          code: fields.code,
          recoveryCode: fields.recoveryCode,
          emailCode: fields.emailCode,
          force: fields.force,
          deviceName: fields.deviceName || props.deviceName,
        }),
      )
    }

    return () => {
      const forms = F.value
      const sso = S.value
      const nameLabel = props.usernameLabel || (props.allowReclaim ? sso.usernameOrEmail : forms.username)
      const buttonText = busy.value
        ? forms.loggingIn
        : bindForce.value
          ? forms.forceLogin
          : props.submitLabel || sso.bindExisting
      const children: ReturnType<typeof h>[] = [
        h(
          "form",
          {
            class: "ak-form",
            onSubmit: (event: Event) => {
              event.preventDefault()
              void submitBind()
            },
          },
          [
            field(
              nameLabel,
              h("input", {
                value: username.value,
                autocomplete: "username",
                onInput: (event: Event) => {
                  username.value = textOf(event)
                },
              }),
            ),
            field(
              forms.password,
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
              ? h(CodeInputRow, {
                  label: forms.captcha,
                  modelValue: captchaCode.value,
                  placeholder: forms.captchaPlaceholder,
                  imageSrc: captchaImage.value || "",
                  buttonText: forms.captchaRefresh,
                  "onUpdate:modelValue": (v: string) => {
                    captchaCode.value = v
                  },
                  onImageClick: () => void loadCaptcha(),
                  onButtonClick: () => void loadCaptcha(),
                })
              : null,
            error.value ? h("p", { class: "ak-error" }, error.value) : null,
            h("button", { type: "submit", disabled: busy.value }, reclaim.value ? sso.reclaimConfirm : buttonText),
          ],
        ),
      ]
      if (mfa.value) {
        children.push(
          h(TwoFactorLoginDialog, {
            client: props.client,
            challenge: mfa.value,
            deviceName: props.deviceName,
            force: bindForce.value || props.force,
            language: locale.value,
            verify: props.completeMfaViaLogin2fa ? undefined : verifyMfa,
            onSuccess: (data: TokenPair) => {
              mfa.value = null
              emit("success", data.access_token, { tokens: data, username: username.value })
            },
            onExpired: () => {
              mfa.value = null
            },
            onCancel: () => {
              mfa.value = null
            },
          }),
        )
      }
      return h("div", children)
    }
  },
})
