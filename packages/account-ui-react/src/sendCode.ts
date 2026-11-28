import { useCallback, useEffect, useRef, useState } from "react"
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
  const [sending, setSending] = useState(false)
  const [left, setLeft] = useState(0)
  const [boundEmail, setBoundEmail] = useState("")
  const [info, setInfo] = useState("")
  const [error, setError] = useState("")
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const boundRef = useRef("")
  const leftRef = useRef(0)

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  const start = useCallback(
    (seconds: number) => {
      stop()
      const next = Math.max(0, Math.floor(seconds))
      leftRef.current = next
      setLeft(next)
      if (next <= 0) return
      timer.current = setInterval(() => {
        const value = leftRef.current - 1
        leftRef.current = value
        if (value <= 0) stop()
        setLeft(value <= 0 ? 0 : value)
      }, 1000)
    },
    [stop],
  )

  useEffect(() => () => stop(), [stop])

  function normalized(email?: string) {
    return String(email || "").trim()
  }

  function canSend(email?: string) {
    return requireEmail ? isSimpleEmail(email || "") : true
  }

  function coolingFor(email?: string) {
    if (left <= 0) return false
    if (!requireEmail) return true
    const current = normalized(email)
    return !current || current === boundEmail
  }

  function buttonDisabled(email?: string) {
    return sending || !canSend(email) || coolingFor(email)
  }

  function buttonText(labels: SendCodeLabelBag, idle: string, email?: string) {
    if (sending) return labels.sending
    if (coolingFor(email)) return interpolate(labels.resendIn, { s: left })
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
    setError("")
    setInfo("")
    if (!canSend(email)) {
      setError(
        formatError(
          new AccountApiError("EMAIL_INVALID", 400, { detail: { code: "EMAIL_INVALID" }, code: "EMAIL_INVALID" }),
          opts.labels,
          opts.locale,
        ),
      )
      return false
    }
    setSending(true)
    try {
      const result = (await send()) || {}
      const sentEmail = String((result as { email?: string }).email || email || "")
      boundRef.current = sentEmail
      setBoundEmail(sentEmail)
      const text =
        typeof opts.successText === "function"
          ? opts.successText(result, sentEmail)
          : opts.successText || sendCodeSuccessText(opts.labels, sentEmail)
      setInfo(text)
      start(cooldownFromResult(result as { cooldown?: number }))
      return true
    } catch (e) {
      const code = errorCodeOf(e)
      let text = formatError(e, opts.labels, opts.locale)
      const hint = code && opts.extraHints?.[code]
      if (hint) text = `${text} ${hint}`
      setInfo("")
      setError(text)
      opts.onError?.(e)
      if (isSendCodeRateLimited(code)) {
        boundRef.current = email
        setBoundEmail(email)
        start(retryAfterFromError(e))
      }
      return false
    } finally {
      setSending(false)
    }
  }

  function reset() {
    stop()
    setSending(false)
    leftRef.current = 0
    setLeft(0)
    boundRef.current = ""
    setBoundEmail("")
    setInfo("")
    setError("")
  }

  return { sending, left, boundEmail, info, error, canSend, buttonDisabled, buttonText, run, reset, setError, setInfo }
}
