import { useMemo, useState, type FormEvent } from "react"
import { AccountApiError, ensureAccountStyle, type AccountClient, type BindExistingPayload, type TokenPair } from "./client"
import { CodeInputRow } from "./authShell"
import { useAccountI18n, useKitLocale } from "./i18n"
import { resolveFormLabels, resolveSsoLabels, type FormLabels, type SsoLabels } from "./labels"
import { errorCodeOf, getMfaChallenge, type MfaChallenge } from "./mfa"
import { TwoFactorLoginDialog, type TwoFactorVerifyPayload } from "./twoFactor"
import { formatError, interpolate, type DeepPartial } from "./utils"

export type BindExistingSuccessExtra = { tokens?: TokenPair; username?: string }

export function BindExistingAccountForm({
  client,
  bindTicket,
  bindExisting,
  deviceName = "",
  force = false,
  language,
  labels,
  ssoLabels,
  defaultUsername = "",
  usernameLabel,
  submitLabel,
  allowReclaim = false,
  completeMfaViaLogin2fa = false,
  onSuccess,
  onConflict,
}: {
  client: AccountClient
  bindTicket: string
  bindExisting: (payload: BindExistingPayload) => Promise<TokenPair>
  deviceName?: string
  force?: boolean
  language?: string
  labels?: DeepPartial<FormLabels> | null
  ssoLabels?: DeepPartial<SsoLabels> | null
  defaultUsername?: string
  usernameLabel?: string
  submitLabel?: string
  allowReclaim?: boolean
  /** WeChat: complete 2FA via kit ``POST /login/2fa``. SSO: re-POST bind-existing. */
  completeMfaViaLogin2fa?: boolean
  onSuccess: (token: string, extra?: BindExistingSuccessExtra) => void
  onConflict?: (error: unknown) => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const { messages } = useAccountI18n()
  const F = useMemo(() => resolveFormLabels(locale, labels, messages), [locale, labels, messages])
  const S = useMemo(() => resolveSsoLabels(locale, ssoLabels, messages), [locale, ssoLabels, messages])
  const [username, setUsername] = useState(defaultUsername)
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [bindForce, setBindForce] = useState(false)
  const [captchaNeeded, setCaptchaNeeded] = useState(false)
  const [captchaId, setCaptchaId] = useState("")
  const [captchaImage, setCaptchaImage] = useState("")
  const [captchaCode, setCaptchaCode] = useState("")
  const [mfa, setMfa] = useState<(MfaChallenge & { username?: string }) | null>(null)
  const [reclaim, setReclaim] = useState(false)
  const [orphanUsername, setOrphanUsername] = useState("")
  const [passedChallengeToken, setPassedChallengeToken] = useState("")

  async function loadCaptcha() {
    setCaptchaId("")
    setCaptchaImage("")
    setCaptchaCode("")
    if (typeof client.captcha !== "function") return
    try {
      const data = await client.captcha()
      setCaptchaId(data.captcha_id || "")
      setCaptchaImage(data.image_base64 ? `data:image/png;base64,${data.image_base64}` : "")
    } catch {
      setError(F.captchaLoadFailed)
    }
  }

  function payload(extra: Partial<BindExistingPayload> = {}): BindExistingPayload {
    return {
      bindTicket,
      username: username.trim(),
      password,
      force: bindForce || force || extra.force,
      deviceName,
      captchaId: extra.captchaId,
      captchaCode: extra.captchaCode,
      code: extra.code,
      recoveryCode: extra.recoveryCode,
      emailCode: extra.emailCode,
      reclaim: reclaim || extra.reclaim,
      challengeToken: extra.challengeToken || passedChallengeToken || undefined,
    }
  }

  async function submitBind(event?: FormEvent, extra: Partial<BindExistingPayload> = {}) {
    if (event) event.preventDefault()
    if (busy || !bindTicket) return
    setError("")
    const usedCaptcha = captchaNeeded
    if (usedCaptcha && (!captchaId || !captchaCode.trim()) && extra.captchaCode === undefined) {
      setError(F.captchaEnter)
      return
    }
    setBusy(true)
    try {
      const tokens = await bindExisting(
        payload({
          captchaId: usedCaptcha ? captchaId : undefined,
          captchaCode: usedCaptcha ? captchaCode.trim() : undefined,
          ...extra,
        }),
      )
      setCaptchaNeeded(false)
      setPassedChallengeToken("")
      onSuccess(tokens.access_token, { tokens, username })
    } catch (err) {
      const body = err instanceof AccountApiError ? err.body : null
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail?: { code?: string; device_name?: string; captcha_required?: boolean; orphan_username?: string } | string }).detail
          : null
      const info = detail && typeof detail === "object" ? detail : null
      const status = err instanceof AccountApiError ? err.status : 0
      const code = info?.code || (err instanceof AccountApiError ? err.code : "") || ""
      if (usedCaptcha) setCaptchaNeeded(false)
      if (status === 428 || code === "CAPTCHA_REQUIRED" || code === "CAPTCHA_INVALID" || info?.captcha_required) {
        setCaptchaNeeded(true)
        await loadCaptcha()
        setError(
          code === "CAPTCHA_INVALID"
            ? F.captchaInvalid
            : status === 428 || code === "CAPTCHA_REQUIRED"
              ? F.captchaEnter
              : formatError(err, F, locale),
        )
      } else if (status === 409 && code === "ALREADY_LOGGED_IN") {
        setBindForce(true)
        onConflict?.(err)
        setError(interpolate(F.alreadyLoggedIn, { device: info?.device_name || F.errors.UNKNOWN_DEVICE }))
      } else if (applyOrphanPending(err, info, code, status)) {
        /* reclaim confirm on the form */
      } else {
        const challenge = getMfaChallenge(err)
        if (challenge) {
          setMfa({ ...challenge, bindTicket: challenge.bindTicket || bindTicket, username })
          return
        }
        setError(formatError(err, F, locale))
      }
    } finally {
      setBusy(false)
    }
  }

  function applyOrphanPending(
    err: unknown,
    info: { orphan_username?: string } | null,
    code: string,
    status: number,
  ) {
    if (!allowReclaim || (status !== 409 && status !== 400) || code !== "SSO_ORPHAN_PENDING") return false
    setReclaim(true)
    const orphan = String(info?.orphan_username || errorParamsUsername(err) || "")
    setOrphanUsername(orphan)
    setError(interpolate(S.reclaimHint, { username: orphan || "—" }))
    setMfa(null)
    return true
  }

  async function verifyMfa(fields: TwoFactorVerifyPayload) {
    if (fields.force) setBindForce(true)
    return bindExisting(
      payload({
        code: fields.code,
        recoveryCode: fields.recoveryCode,
        emailCode: fields.emailCode,
        force: fields.force,
        deviceName: fields.deviceName || deviceName,
        challengeToken: fields.challengeToken,
      }),
    )
  }

  function handleMfaOuterError(err: unknown) {
    const status = err instanceof AccountApiError ? err.status : 0
    const code = errorCodeOf(err) || (err instanceof AccountApiError ? err.code : "") || ""
    const body = err instanceof AccountApiError ? err.body : null
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail?: { orphan_username?: string } | string }).detail
        : null
    const info = detail && typeof detail === "object" ? detail : null
    const token = mfa?.challengeToken || ""
    if (applyOrphanPending(err, info, code, status)) {
      if (token) setPassedChallengeToken(token)
      return true
    }
    return false
  }

  function handleUsernameChange(next: string) {
    if (reclaim) setError("")
    setUsername(next)
    setPassedChallengeToken("")
    setReclaim(false)
    setOrphanUsername("")
  }

  const nameLabel = usernameLabel || (allowReclaim ? S.usernameOrEmail : F.username)
  const buttonText = busy ? F.loggingIn : bindForce ? F.forceLogin : submitLabel || S.bindExisting

  return (
    <>
      <form className="ak-form" onSubmit={(event) => void submitBind(event)}>
        <label className="ak-field">
          {nameLabel}
          <input value={username} autoComplete="username" onChange={(e) => handleUsernameChange(e.target.value)} />
        </label>
        <label className="ak-field">
          {F.password}
          <input type="password" value={password} autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
        </label>
        {captchaNeeded ? (
          <CodeInputRow
            label={F.captcha}
            value={captchaCode}
            placeholder={F.captchaPlaceholder}
            onChange={setCaptchaCode}
            imageSrc={captchaImage || undefined}
            onImageClick={() => void loadCaptcha()}
            buttonText={F.captchaRefresh}
            onButtonClick={() => void loadCaptcha()}
          />
        ) : null}
        {error ? <p className="ak-error">{error}</p> : null}
        <button type="submit" disabled={busy}>
          {reclaim ? S.reclaimConfirm : buttonText}
        </button>
      </form>
      {mfa ? (
        <TwoFactorLoginDialog
          client={client}
          challenge={mfa}
          deviceName={deviceName}
          force={bindForce || force}
          language={locale}
          verify={completeMfaViaLogin2fa ? undefined : verifyMfa}
          onError={handleMfaOuterError}
          onSuccess={(data) => {
            setMfa(null)
            setPassedChallengeToken("")
            onSuccess(data.access_token, { tokens: data, username: mfa.username })
          }}
          onExpired={() => {
            setMfa(null)
            setPassedChallengeToken("")
          }}
          onCancel={() => {
            setMfa(null)
            setPassedChallengeToken("")
          }}
        />
      ) : null}
    </>
  )
}

function errorParamsUsername(error: unknown): string {
  if (!(error instanceof AccountApiError) || !error.body || typeof error.body !== "object") return ""
  const body = error.body as { params?: { orphan_username?: unknown } }
  const value = body.params?.orphan_username
  return typeof value === "string" ? value : ""
}
