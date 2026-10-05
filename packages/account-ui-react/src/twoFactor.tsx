import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { ensureAccountStyle, type AccountClient, type LoginSecondFactorResult, type TrustedDevice, type TwoFactorStatus } from "./client"
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
import { formatDateTime, interpolate, resolveLocale, type DeepPartial } from "./utils"

function btnClass(kind: "primary" | "outline" | "danger" | "link", extra = "") {
  if (kind === "link") return `ak-link${extra ? ` ${extra}` : ""}`
  return `ak-btn${kind === "outline" ? " ak-btn-outline" : kind === "danger" ? " ak-btn-danger" : ""}${extra ? ` ${extra}` : ""}`
}

export function TwoFactorSettings({
  client,
  token,
  username = "",
  language = "zh",
  labels,
  renderQr,
  className = "",
  storageKey,
  brand = "account-kit",
  onEnabled,
  onDisabled,
  onUpdated,
}: {
  client: AccountClient
  token: string
  username?: string
  language?: string
  labels?: DeepPartial<TwoFactorLabels> | null
  renderQr?: RenderQr
  className?: string
  storageKey?: string
  brand?: string
  onEnabled?: (result: { enabled: boolean; recovery_codes: string[] }) => void
  onDisabled?: () => void
  onUpdated?: (status: TwoFactorStatus) => void
}) {
  ensureAccountStyle()
  const L = useMemo(() => resolveTwoFactorLabels(language, labels), [language, labels])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState("")
  const [status, setStatus] = useState<TwoFactorStatus | null>(null)
  const [devices, setDevices] = useState<TrustedDevice[]>([])
  const [mode, setMode] = useState<"overview" | "setup-password" | "setup-scan" | "recovery" | "disable" | "regenerate">("overview")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [recoveryCode, setRecoveryCode] = useState("")
  const [emailCode, setEmailCode] = useState("")
  const [factor, setFactor] = useState<SecondFactor>(FACTOR_TOTP)
  const [setupSecret, setSetupSecret] = useState("")
  const [qrDataUrl, setQrDataUrl] = useState("")
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [savedAck, setSavedAck] = useState(false)
  const [emailMasked, setEmailMasked] = useState("")
  const [cooldown, setCooldown] = useState(0)
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function errText(e: unknown) {
    return twoFactorErrorMessage(e, L)
  }

  function startCooldown(sec = 60) {
    setCooldown(sec)
    if (cooldownRef.current) clearInterval(cooldownRef.current)
    cooldownRef.current = setInterval(() => {
      setCooldown((value) => {
        if (value <= 1 && cooldownRef.current) clearInterval(cooldownRef.current)
        return value <= 1 ? 0 : value - 1
      })
    }, 1000)
  }

  async function load() {
    setLoading(true)
    setLoadError("")
    try {
      const next = await client.twoFactorStatus(token)
      setStatus(next)
      setDevices(next.enabled ? await client.listTrustedDevices(token) : [])
      onUpdated?.(next)
    } catch (e) {
      setLoadError(errText(e))
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setMode("overview")
    setError("")
    setPassword("")
    setCode("")
    setRecoveryCode("")
    setFactor(FACTOR_TOTP)
    setSetupSecret("")
    setQrDataUrl("")
    setEmailCode("")
    setEmailMasked("")
    setSavedAck(false)
  }

  function begin(next: typeof mode) {
    reset()
    setInfo("")
    setMode(next)
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true)
    setError("")
    try {
      await fn()
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  async function sendEmail() {
    await run(async () => {
      try {
        const res = await client.sendDisableEmailCode(token, resolveLocale(language))
        setEmailMasked(res.email || "")
        startCooldown(Number(res.cooldown) || 60)
      } catch (e) {
        if (errorCodeOf(e) === "EMAIL_CODE_TOO_FREQUENT") startCooldown()
        throw e
      }
    })
  }

  useEffect(() => {
    void load()
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, token])

  const factorInputs = { code, recoveryCode, emailCode }
  const codeReady = canSubmitFactor(factor, factorInputs)
  const factorLabel = factor === FACTOR_RECOVERY ? L.recoveryCode : factor === FACTOR_EMAIL ? L.emailCode : L.enterCode

  function factorLinks(allowEmail: boolean) {
    return (
      <div className="ak-links" style={{ flexDirection: "row", flexWrap: "wrap", gap: "6px 16px", marginTop: 4 }}>
        {factor !== FACTOR_TOTP ? (
          <button type="button" className="ak-link" onClick={() => { setFactor(FACTOR_TOTP); setError("") }}>
            {L.login.useApp}
          </button>
        ) : null}
        {factor !== FACTOR_RECOVERY ? (
          <button type="button" className="ak-link" onClick={() => { setFactor(FACTOR_RECOVERY); setError("") }}>
            {L.login.useRecovery}
          </button>
        ) : null}
        {allowEmail && factor !== FACTOR_EMAIL ? (
          <button
            type="button"
            className="ak-link"
            onClick={() => {
              setFactor(FACTOR_EMAIL)
              setError("")
              if (cooldown <= 0) void sendEmail()
            }}
          >
            {L.skipDisable}
          </button>
        ) : null}
      </div>
    )
  }

  function totpInput(value: string, onSet: (v: string) => void, placeholder = "000000") {
    return (
      <input
        className="ak-input ak-code"
        value={value}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        placeholder={placeholder}
        onChange={(event) => onSet(normalizeTotpInput(event.target.value))}
      />
    )
  }

  let body
  if (loading) body = <div className="ak-muted">{L.loading}</div>
  else if (loadError) body = <div className="ak-error">{loadError}</div>
  else if (mode === "recovery") {
    body = (
      <div className="ak-section">
        <h3>{L.recoveryTitle}</h3>
        <p className="ak-hint">{L.recoveryHint}</p>
        <ul className="ak-codes">
          {recoveryCodes.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div className="ak-actions">
          <button
            type="button"
            className={btnClass("outline")}
            onClick={() => {
              void navigator.clipboard?.writeText(recoveryCodes.join("\n")).then(() => setInfo(L.copied))
            }}
          >
            {L.copy}
          </button>
          <button
            type="button"
            className={btnClass("outline")}
            onClick={() => {
              const text = recoveryCodesText(recoveryCodes, { username, brand })
              const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }))
              const a = document.createElement("a")
              a.href = url
              a.download = `recovery-codes-${username || "account"}.txt`
              document.body.appendChild(a)
              a.click()
              a.remove()
              setTimeout(() => URL.revokeObjectURL(url), 1000)
            }}
          >
            {L.download}
          </button>
        </div>
        {info ? <p className="ak-success">{info}</p> : null}
        <label className="ak-check">
          <input type="checkbox" checked={savedAck} onChange={(event) => setSavedAck(event.target.checked)} />
          <span>{L.recoverySavedAck}</span>
        </label>
        <div className="ak-actions">
          <button
            type="button"
            className={btnClass("primary")}
            disabled={!savedAck}
            onClick={() => {
              setRecoveryCodes([])
              reset()
              setInfo(L.enabledOk)
              void load()
            }}
          >
            {L.done}
          </button>
        </div>
      </div>
    )
  } else if (mode === "setup-password") {
    body = (
      <form
        className="ak-section"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void run(async () => {
            const res = await client.twoFactorSetup(token, password)
            setPassword("")
            setSetupSecret(res.secret)
            setQrDataUrl(await renderQrDataUrl(res.otpauth_uri, renderQr))
            setMode("setup-scan")
          })
        }}
      >
        <label className="ak-field">
          {L.currentPassword}
          <input className="ak-input" type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p className="ak-error">{error}</p> : null}
        <div className="ak-actions">
          <button type="button" className={btnClass("outline")} disabled={busy} onClick={reset}>
            {L.cancel}
          </button>
          <button type="submit" className={btnClass("primary")} disabled={busy || !password}>
            {L.next}
          </button>
        </div>
      </form>
    )
  } else if (mode === "setup-scan") {
    body = (
      <form
        className="ak-section"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void run(async () => {
            const res = await client.twoFactorEnable(token, code)
            setRecoveryCodes(res.recovery_codes || [])
            setSetupSecret("")
            setQrDataUrl("")
            setCode("")
            setSavedAck(false)
            setMode("recovery")
            onEnabled?.(res)
          })
        }}
      >
        <ol className="ak-steps">
          <li>{L.scanStep1}</li>
          <li>{L.scanStep2}</li>
        </ol>
        <div className="ak-qr-wrap">
          {qrDataUrl ? <img src={qrDataUrl} className="ak-qr" alt="QR" /> : <p className="ak-muted">{L.qrUnavailable}</p>}
          <div className="ak-secret">
            <span className="ak-muted">{L.manualEntry}</span>
            <code>{formatSecret(setupSecret)}</code>
            <button type="button" className="ak-link" onClick={() => void navigator.clipboard?.writeText(setupSecret).then(() => setInfo(L.copied))}>
              {L.copy}
            </button>
          </div>
        </div>
        <label className="ak-field">
          {L.enterCode}
          {totpInput(code, setCode)}
        </label>
        {error ? <p className="ak-error">{error}</p> : null}
        <div className="ak-actions">
          <button type="button" className={btnClass("outline")} disabled={busy} onClick={reset}>
            {L.cancel}
          </button>
          <button type="submit" className={btnClass("primary")} disabled={busy || code.length !== 6}>
            {L.enable}
          </button>
        </div>
      </form>
    )
  } else if (mode === "disable" || mode === "regenerate") {
    body = (
      <form
        className="ak-section"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          void run(async () => {
            const payload = { password, ...secondFactorFields(factor, factorInputs) }
            if (mode === "disable") {
              await client.twoFactorDisable(token, payload)
              if (username) clearTrustedDeviceTokensForUser(username, storageKey)
              reset()
              setInfo(L.disabledOk)
              onDisabled?.()
              await load()
            } else {
              const res = await client.regenerateRecoveryCodes(token, payload)
              reset()
              setRecoveryCodes(res.recovery_codes || [])
              setMode("recovery")
            }
          })
        }}
      >
        <h3>{mode === "disable" ? L.disableTitle : L.regenerateTitle}</h3>
        {mode === "disable" ? <p className="ak-hint">{L.disableHint}</p> : null}
        <label className="ak-field">
          {L.currentPassword}
          <input className="ak-input" type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} />
        </label>
        <label className="ak-field">
          {factorLabel}
          {factor === FACTOR_TOTP ? (
            totpInput(code, setCode)
          ) : factor === FACTOR_RECOVERY ? (
            <input className="ak-input" value={recoveryCode} autoComplete="off" placeholder="xxxx-xxxx" onChange={(event) => setRecoveryCode(event.target.value)} />
          ) : (
            <span className="ak-row">
              {totpInput(emailCode, setEmailCode, L.emailCodePlaceholder)}
              <button type="button" className={btnClass("outline")} disabled={busy || cooldown > 0} onClick={() => void sendEmail()}>
                {cooldown > 0 ? interpolate(L.resendIn, { s: cooldown }) : L.sendEmailCode}
              </button>
            </span>
          )}
        </label>
        {factor === FACTOR_EMAIL && emailMasked ? <p className="ak-muted">{interpolate(L.emailSentTo, { email: emailMasked })}</p> : null}
        {factorLinks(mode === "disable" && !!status?.email_available)}
        {error ? <p className="ak-error">{error}</p> : null}
        <div className="ak-actions">
          <button type="button" className={btnClass("outline")} disabled={busy} onClick={reset}>
            {L.cancel}
          </button>
          <button type="submit" className={btnClass(mode === "disable" ? "danger" : "primary")} disabled={busy || !password || !codeReady}>
            {mode === "disable" ? L.disable : L.regenerate}
          </button>
        </div>
      </form>
    )
  } else if (status) {
    body = (
      <div className="ak-section">
        {info ? <p className="ak-success">{info}</p> : null}
        {!status.enabled ? (
          <div className="ak-actions">
            <button type="button" className={btnClass("primary")} onClick={() => begin("setup-password")}>
              {L.enable}
            </button>
          </div>
        ) : (
          <>
            <p className="ak-muted">{interpolate(L.recoveryRemaining, { n: status.recovery_codes_remaining })}</p>
            <div className="ak-actions">
              <button type="button" className={btnClass("outline")} onClick={() => begin("regenerate")}>
                {L.regenerate}
              </button>
              <button type="button" className={btnClass("danger")} onClick={() => begin("disable")}>
                {L.disable}
              </button>
            </div>
            <div className="ak-devices">
              <div className="ak-tf-head">
                <h3>{L.trustedDevices}</h3>
                {devices.length ? (
                  <button
                    type="button"
                    className="ak-link ak-danger"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await client.revokeAllTrustedDevices(token)
                        setDevices([])
                        if (username) clearTrustedDeviceTokensForUser(username, storageKey)
                      })
                    }
                  >
                    {L.revokeAll}
                  </button>
                ) : null}
              </div>
              <p className="ak-muted">{interpolate(L.trustedDevicesHint, { days: status.trusted_device_days })}</p>
              {!devices.length ? (
                <p className="ak-muted">{L.noTrustedDevices}</p>
              ) : (
                <ul className="ak-device-list">
                  {devices.map((device) => (
                    <li key={device.id}>
                      <div>
                        <div className="ak-device-name">{device.device_name}</div>
                        <div className="ak-muted">
                          {L.lastUsed} {formatDateTime(device.last_used_at)} · {L.expires} {formatDateTime(device.expires_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="ak-btn ak-btn-outline ak-btn-small"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await client.revokeTrustedDevice(token, device.id)
                            setDevices((items) => items.filter((item) => item.id !== device.id))
                          })
                        }
                      >
                        {L.revoke}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div className={["ak-tf", className].filter(Boolean).join(" ")}>
      <div className="ak-tf-head">
        <h2>{L.title}</h2>
        {status ? <span className={`ak-badge ${status.enabled ? "ak-badge-on" : "ak-badge-off"}`}>{status.enabled ? L.statusOn : L.statusOff}</span> : null}
      </div>
      <p className="ak-hint">{L.description}</p>
      {body}
    </div>
  )
}

export function TwoFactorLoginDialog({
  client,
  challenge,
  deviceName = "",
  force = false,
  trustedDays = 0,
  language = "zh",
  labels,
  className = "",
  scope = "",
  storageKey,
  onSuccess,
  onExpired,
  onCancel,
}: {
  client: AccountClient
  challenge: MfaChallenge | Record<string, unknown>
  deviceName?: string
  force?: boolean
  trustedDays?: number
  language?: string
  labels?: DeepPartial<TwoFactorLabels> | null
  className?: string
  scope?: string
  storageKey?: string
  onSuccess: (data: LoginSecondFactorResult) => void
  onExpired?: (message: string) => void
  onCancel?: () => void
}) {
  ensureAccountStyle()
  const L = useMemo(() => resolveTwoFactorLabels(language, labels), [language, labels])
  const info = normalizeChallenge(challenge)
  const [mode, setMode] = useState<"code" | "conflict">("code")
  const [factor, setFactor] = useState<SecondFactor>(FACTOR_TOTP)
  const [code, setCode] = useState("")
  const [recoveryCode, setRecoveryCode] = useState("")
  const [emailCode, setEmailCode] = useState("")
  const [trustDevice, setTrustDevice] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [conflictDevice, setConflictDevice] = useState("")
  const [emailMasked, setEmailMasked] = useState("")
  const [cooldown, setCooldown] = useState(0)
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function startCooldown(sec = 60) {
    setCooldown(sec)
    if (cooldownRef.current) clearInterval(cooldownRef.current)
    cooldownRef.current = setInterval(() => {
      setCooldown((value) => {
        if (value <= 1 && cooldownRef.current) clearInterval(cooldownRef.current)
        return value <= 1 ? 0 : value - 1
      })
    }, 1000)
  }

  useEffect(
    () => () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current)
    },
    [],
  )

  const factorInputs = { code, recoveryCode, emailCode }
  const canSubmit = canSubmitFactor(factor, factorInputs)
  const days = trustedDays || info?.trustedDays || 30
  const hint = factor === FACTOR_RECOVERY ? L.login.recoveryHint : factor === FACTOR_EMAIL ? L.login.emailHint : L.login.hint

  async function submit(nextForce: boolean) {
    if (busy || !info) return
    setBusy(true)
    setError("")
    try {
      const fields = mode === "conflict" ? { code: "", recoveryCode: "", emailCode: "" } : secondFactorFields(factor, factorInputs)
      const data = await client.loginSecondFactor({
        challengeToken: info.challengeToken,
        ...fields,
        trustDevice,
        force: nextForce,
        deviceName,
      })
      if (data.trusted_device_token && scope) {
        saveTrustedDeviceToken(scope, data.trusted_device_token, data.trusted_device_expires_at, storageKey)
      }
      onSuccess(data)
    } catch (e) {
      const status = e && typeof e === "object" && "status" in e ? Number((e as { status: number }).status) : 0
      const errCode = errorCodeOf(e)
      if (status === 409 && errCode === "ALREADY_LOGGED_IN") {
        const detail = e && typeof e === "object" && "body" in e ? (e as { body?: { detail?: { device_name?: string } } }).body?.detail : null
        setConflictDevice(detail?.device_name || "")
        setMode("conflict")
      } else if (errCode === "MFA_CHALLENGE_INVALID" || errCode === "MFA_TOO_MANY_ATTEMPTS") {
        onExpired?.(twoFactorErrorMessage(e, L))
      } else {
        setError(twoFactorErrorMessage(e, L))
        if (factor === FACTOR_EMAIL) setEmailCode("")
        else setCode("")
      }
    } finally {
      setBusy(false)
    }
  }

  async function sendEmail() {
    if (busy || !info) return
    setBusy(true)
    setError("")
    try {
      const res = await client.sendLoginEmailCode(info.challengeToken, resolveLocale(language))
      setEmailMasked(res.email || "")
      startCooldown(Number(res.cooldown) || 60)
    } catch (e) {
      const errCode = errorCodeOf(e)
      if (errCode === "MFA_CHALLENGE_INVALID") onExpired?.(twoFactorErrorMessage(e, L))
      else setError(twoFactorErrorMessage(e, L))
      if (errCode === "EMAIL_CODE_TOO_FREQUENT") startCooldown()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className={["ak-overlay", className].filter(Boolean).join(" ")}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel?.()
      }}
    >
      {mode === "conflict" ? (
        <div className="ak-dialog" role="dialog" aria-modal="true">
          <h3>{L.login.alreadyLoggedInTitle}</h3>
          <p className="ak-hint">{interpolate(L.login.alreadyLoggedInBody, { device: conflictDevice || L.login.unknownDevice })}</p>
          <p className="ak-warn">{L.login.unsavedDataWarning}</p>
          {error ? <div className="ak-error">{error}</div> : null}
          <div className="ak-actions" style={{ justifyContent: "flex-end" }}>
            <button type="button" className={btnClass("outline")} disabled={busy} onClick={() => { if (!busy) onCancel?.() }}>
              {L.login.forceLoginCancel}
            </button>
            <button type="button" className={btnClass("primary")} disabled={busy} onClick={() => void submit(true)}>
              {L.login.forceLoginConfirm}
            </button>
          </div>
        </div>
      ) : (
        <div className="ak-dialog" role="dialog" aria-modal="true">
          <h3>{factor === FACTOR_EMAIL ? L.login.emailTitle : L.login.title}</h3>
          <p className="ak-hint">{hint}</p>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void submit(force)
            }}
          >
            {factor === FACTOR_TOTP ? (
              <input
                className="ak-input ak-code"
                value={code}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                placeholder="000000"
                onChange={(event) => {
                  const next = normalizeTotpInput(event.target.value)
                  setCode(next)
                  if (next.length === 6 && !busy) void submit(force)
                }}
              />
            ) : factor === FACTOR_RECOVERY ? (
              <input
                className="ak-input"
                value={recoveryCode}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="xxxx-xxxx"
                onChange={(event) => setRecoveryCode(event.target.value)}
              />
            ) : (
              <>
                <span className="ak-row">
                  <input
                    className="ak-input ak-code"
                    value={emailCode}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={7}
                    placeholder={L.emailCodePlaceholder}
                    onChange={(event) => setEmailCode(normalizeTotpInput(event.target.value))}
                  />
                  <button type="button" className={btnClass("outline")} disabled={busy || cooldown > 0} onClick={() => void sendEmail()}>
                    {cooldown > 0 ? interpolate(L.resendIn, { s: cooldown }) : L.sendEmailCode}
                  </button>
                </span>
                {emailMasked ? <p className="ak-muted">{interpolate(L.emailSentTo, { email: emailMasked })}</p> : null}
              </>
            )}
            <label className="ak-check">
              <input type="checkbox" checked={trustDevice} onChange={(event) => setTrustDevice(event.target.checked)} />
              <span>{interpolate(L.login.trustDevice, { days })}</span>
            </label>
            {error ? <div className="ak-error">{error}</div> : null}
            <div className="ak-actions" style={{ justifyContent: "flex-end" }}>
              <button type="button" className={btnClass("outline")} disabled={busy} onClick={() => { if (!busy) onCancel?.() }}>
                {L.cancel}
              </button>
              <button type="submit" className={btnClass("primary")} disabled={busy || !canSubmit}>
                {busy ? L.verifying : L.verify}
              </button>
            </div>
          </form>
          <div className="ak-links">
            {factor !== FACTOR_TOTP ? (
              <button type="button" className="ak-link" onClick={() => { setFactor(FACTOR_TOTP); setError("") }}>
                {L.login.useApp}
              </button>
            ) : null}
            {factor !== FACTOR_RECOVERY ? (
              <button type="button" className="ak-link" onClick={() => { setFactor(FACTOR_RECOVERY); setError("") }}>
                {L.login.useRecovery}
              </button>
            ) : null}
            {info?.emailAvailable && factor !== FACTOR_EMAIL ? (
              <button
                type="button"
                className="ak-link"
                onClick={() => {
                  setFactor(FACTOR_EMAIL)
                  setError("")
                  if (cooldown <= 0) void sendEmail()
                }}
              >
                {L.login.skip}
              </button>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
