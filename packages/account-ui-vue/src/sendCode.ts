import { onBeforeUnmount, ref } from "vue"
import { AccountApiError } from "./client"
import {
  cooldownFromResult,
  errorCodeOf,
  formatError,
  interpolate,
  isSendCodeRateLimited,
  isSimpleEmail,
  retryAfterFromError,
} from "./utils"

export type SendCodeLabelBag = {
  sending: string
  sendCode?: string
  resendIn: string
  codeSent?: string
  codeSentTo?: string
  error?: string
  errors?: Record<string, string>
}

export type SendCodeResult = { email?: string; cooldown?: number; status?: string } | void | null

export function sendCodeSuccessText(labels: SendCodeLabelBag, email?: string) {
  if (email && labels.codeSentTo) return interpolate(labels.codeSentTo, { email })
  return labels.codeSent || ""
}

export function useSendCode(options?: { requireEmail?: boolean }) {
  const requireEmail = !!options?.requireEmail
  const sending = ref(false)
  const left = ref(0)
  const boundEmail = ref("")
  const info = ref("")
  const error = ref("")
  let timer: ReturnType<typeof setInterval> | null = null

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function start(seconds: number) {
    stop()
    left.value = Math.max(0, Math.floor(seconds))
    if (left.value <= 0) return
    timer = setInterval(() => {
      left.value -= 1
      if (left.value <= 0) stop()
    }, 1000)
  }

  onBeforeUnmount(stop)

  function normalized(email?: string) {
    return String(email || "").trim()
  }

  function canSend(email?: string) {
    return requireEmail ? isSimpleEmail(email || "") : true
  }

  function coolingFor(email?: string) {
    if (left.value <= 0) return false
    if (!requireEmail) return true
    const current = normalized(email)
    return !current || current === boundEmail.value
  }

  function buttonDisabled(email?: string) {
    return sending.value || !canSend(email) || coolingFor(email)
  }

  function buttonText(labels: SendCodeLabelBag, idle: string, email?: string) {
    if (sending.value) return labels.sending
    if (coolingFor(email)) return interpolate(labels.resendIn, { s: left.value })
    return idle
  }

  async function run(
    send: () => Promise<SendCodeResult>,
    opts: {
      email?: string
      labels: SendCodeLabelBag
      locale?: string
      successText?: string | ((result: SendCodeResult, email: string) => string)
      extraHints?: Record<string, string>
      onError?: (error: unknown) => void
    },
  ) {
    const email = normalized(opts.email)
    error.value = ""
    info.value = ""
    if (!canSend(email)) {
      error.value = formatError(
        new AccountApiError("EMAIL_INVALID", 400, { detail: { code: "EMAIL_INVALID" }, code: "EMAIL_INVALID" }),
        opts.labels,
        opts.locale,
      )
      return false
    }
    sending.value = true
    try {
      const result = (await send()) || {}
      const sentEmail = String((result as { email?: string }).email || email || "")
      boundEmail.value = sentEmail
      info.value =
        typeof opts.successText === "function"
          ? opts.successText(result, sentEmail)
          : opts.successText || sendCodeSuccessText(opts.labels, sentEmail)
      start(cooldownFromResult(result as { cooldown?: number }))
      return true
    } catch (e) {
      info.value = ""
      const code = errorCodeOf(e)
      let text = formatError(e, opts.labels, opts.locale)
      const hint = code && opts.extraHints?.[code]
      if (hint) text = `${text} ${hint}`
      error.value = text
      opts.onError?.(e)
      if (isSendCodeRateLimited(code)) {
        boundEmail.value = email
        start(retryAfterFromError(e))
      }
      return false
    } finally {
      sending.value = false
    }
  }

  function reset() {
    stop()
    sending.value = false
    left.value = 0
    boundEmail.value = ""
    info.value = ""
    error.value = ""
  }

  return { sending, left, boundEmail, info, error, canSend, buttonDisabled, buttonText, run, reset }
}
